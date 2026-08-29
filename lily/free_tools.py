"""Free, no-key public API integrations for Lily.

All providers here are opt-in via natural language and return bounded,
attribution-friendly results. None stores credentials or calls paid tiers
unless the operator configures a separate Lily provider elsewhere.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from .config import settings


class FreeToolsError(RuntimeError):
    pass


class FreeTools:
    def __init__(self) -> None:
        self._timeout = httpx.Timeout(settings.free_api_timeout, connect=8.0)
        self._headers = {"User-Agent": settings.free_api_user_agent}

    async def _get_text(self, url: str, params: dict | None = None) -> str:
        timeout = httpx.Timeout(20.0, connect=8.0)
        headers = {"User-Agent": getattr(self, "api_user_agent", "LilyBot/1.0")}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(url, params=params or {})
            response.raise_for_status()
            return response.text

    async def _get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        merged = dict(self._headers)
        if headers:
            merged.update(headers)
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, headers=merged) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def weather(self, location: str) -> str:
        location = location.strip()[:120]
        if not location:
            raise FreeToolsError("Provide a city or place name.")
        geo = await self._get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
        )
        results = geo.get("results") if isinstance(geo.get("results"), list) else []
        if not results:
            raise FreeToolsError(f"No weather location matched “{location}”.")
        place = results[0]
        forecast = await self._get_json(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        current = forecast.get("current", {})
        code = int(current.get("weather_code", 0))
        label = _WEATHER_CODES.get(code, "Unknown")
        name = f"{place.get('name', location)}, {place.get('country_code', '')}".strip(", ")
        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        daily = forecast.get("daily", {})
        hi = (daily.get("temperature_2m_max") or [None])[0]
        lo = (daily.get("temperature_2m_min") or [None])[0]
        rain = (daily.get("precipitation_probability_max") or [None])[0]
        return (
            f"**Weather — {name}**\n"
            f"Now: {temp}°C (feels {feels}°C) · {label}\n"
            f"Humidity {humidity}% · Wind {wind} km/h\n"
            f"Today: {lo}°C – {hi}°C · Rain chance {rain}%"
        )

    async def crypto_price(self, symbol: str) -> str:
        symbol = symbol.strip().lower()[:40]
        if not symbol:
            raise FreeToolsError("Provide a coin name or symbol, e.g. bitcoin or eth.")
        data = await self._get_json(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": symbol, "vs_currencies": "usd,eur", "include_24hr_change": "true", "include_market_cap": "true"},
        )
        if symbol not in data:
            search = await self._get_json("https://api.coingecko.com/api/v3/search", params={"query": symbol})
            coins = search.get("coins") if isinstance(search.get("coins"), list) else []
            if not coins:
                raise FreeToolsError(f"No cryptocurrency matched “{symbol}”.")
            symbol = str(coins[0]["id"])
            data = await self._get_json(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": symbol, "vs_currencies": "usd,eur", "include_24hr_change": "true", "include_market_cap": "true"},
            )
        row = data.get(symbol, {})
        usd = row.get("usd")
        eur = row.get("eur")
        change = row.get("usd_24h_change")
        cap = row.get("usd_market_cap")
        change_text = f"{change:+.2f}%" if isinstance(change, (int, float)) else "n/a"
        cap_text = f"${cap:,.0f}" if isinstance(cap, (int, float)) else "n/a"
        return f"**{symbol.replace('-', ' ').title()}**\nUSD ${usd:,.4f} · EUR €{eur:,.4f}\n24h {change_text} · MCap {cap_text}"

    async def exchange_rate(self, base: str, target: str, amount: float = 1.0) -> str:
        base = base.strip().upper()[:3]
        target = target.strip().upper()[:3]
        amount = max(0.01, min(float(amount), 1_000_000_000))
        data = await self._get_json(f"https://api.frankfurter.app/latest", params={"from": base, "to": target, "amount": amount})
        rate = (data.get("rates") or {}).get(target)
        if rate is None:
            raise FreeToolsError(f"Could not convert {base} to {target}.")
        return f"**{amount:g} {base} → {target}**\n{amount:g} {base} = {rate:,.4f} {target}\nRate: 1 {base} = {rate / amount:,.6f} {target}"

    async def wikipedia(self, query: str) -> str:
        query = query.strip()[:200]
        if not query:
            raise FreeToolsError("Provide a topic to look up on Wikipedia.")
        data = await self._get_json(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(query.replace(" ", "_")),
        )
        title = str(data.get("title") or query)
        extract = str(data.get("extract") or "")[:1200]
        url = str(data.get("content_urls", {}).get("desktop", {}).get("page") or f"https://en.wikipedia.org/wiki/{quote(title)}")
        if not extract:
            raise FreeToolsError(f"Wikipedia has no summary for “{query}”.")
        return f"**{title}**\n{extract}\n\n{url}"

    async def define_word(self, word: str) -> str:
        word = re.sub(r"[^a-zA-Z\-' ]", "", word.strip())[:60]
        if not word:
            raise FreeToolsError("Provide a word to define.")
        data = await self._get_json(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(word)}")
        if not isinstance(data, list) or not data:
            raise FreeToolsError(f"No definition found for “{word}”.")
        entry = data[0]
        phonetic = str(entry.get("phonetic") or "")
        meanings = entry.get("meanings") if isinstance(entry.get("meanings"), list) else []
        lines = [f"**{entry.get('word', word)}** {phonetic}".strip()]
        for meaning in meanings[:3]:
            part = str(meaning.get("partOfSpeech") or "definition")
            defs = meaning.get("definitions") if isinstance(meaning.get("definitions"), list) else []
            for item in defs[:2]:
                definition = str(item.get("definition") or "").strip()
                example = str(item.get("example") or "").strip()
                if definition:
                    lines.append(f"• *{part}*: {definition[:280]}")
                if example:
                    lines.append(f"  _{example[:180]}_")
        return "\n".join(lines)[:3500]

    async def anime_search(self, query: str) -> str:
        query = query.strip()[:120]
        if not query:
            raise FreeToolsError("Provide an anime title to search.")
        data = await self._get_json(f"https://api.jikan.moe/v4/anime", params={"q": query, "limit": 5, "sfw": "true"})
        items = data.get("data") if isinstance(data.get("data"), list) else []
        if not items:
            raise FreeToolsError(f"No anime matched “{query}”.")
        lines = [f"**Anime results for “{query}”**"]
        for item in items[:5]:
            title = item.get("title") or item.get("title_english") or "Untitled"
            score = item.get("score")
            episodes = item.get("episodes") or "?"
            status = item.get("status") or "unknown"
            url = item.get("url") or ""
            lines.append(f"• **{title}** — {score or 'n/a'}/10 · {episodes} eps · {status}\n  {url}")
        return "\n".join(lines)[:3500]

    async def github_repo(self, repo: str) -> str:
        repo = repo.strip().strip("/")[:120]
        if repo.startswith("https://github.com/"):
            repo = repo.split("github.com/", 1)[1]
        if repo.count("/") != 1:
            raise FreeToolsError("Use owner/repository or a full GitHub URL.")
        data = await self._get_json(f"https://api.github.com/repos/{repo}")
        stars = data.get("stargazers_count", 0)
        forks = data.get("forks_count", 0)
        issues = data.get("open_issues_count", 0)
        language = data.get("language") or "n/a"
        desc = str(data.get("description") or "No description.")[:400]
        license_name = (data.get("license") or {}).get("spdx_id") or "n/a"
        updated = str(data.get("updated_at") or "")[:10]
        return (
            f"**{data.get('full_name', repo)}**\n"
            f"⭐ {stars:,} · 🍴 {forks:,} · Issues {issues:,}\n"
            f"Language: {language} · License: {license_name} · Updated {updated}\n"
            f"{desc}\n{data.get('html_url', '')}"
        )

    async def world_time(self, city: str) -> str:
        city = city.strip().lower().replace(" ", "_")[:80]
        if not city:
            raise FreeToolsError("Provide a city or timezone, e.g. London or Europe/Berlin.")
        try:
            data = await self._get_json(f"https://worldtimeapi.org/api/timezone/Etc/UTC")
            zones = await self._get_json("https://worldtimeapi.org/api/timezone")
        except Exception:
            zones = []
        chosen = None
        if "/" in city:
            chosen = city
        else:
            for zone in zones if isinstance(zones, list) else []:
                if city in zone.lower():
                    chosen = zone
                    break
        if not chosen:
            raise FreeToolsError(f"No timezone matched “{city}”. Try Europe/London or America/New_York.")
        data = await self._get_json(f"https://worldtimeapi.org/api/timezone/{chosen}")
        return (
            f"**Time in {data.get('timezone', chosen)}**\n"
            f"{data.get('datetime', '')[:19].replace('T', ' ')} ({data.get('abbreviation', '')})\n"
            f"UTC offset {data.get('utc_offset', '')} · Weekday {data.get('day_of_week', '')}"
        )

    async def daily_quote(self) -> str:
        data = await self._get_json("https://api.quotable.io/random", params={"maxLength": 180})
        content = str(data.get("content") or "")
        author = str(data.get("author") or "Unknown")
        tags = ", ".join(str(tag) for tag in (data.get("tags") or [])[:4])
        return f"“{content}”\n— **{author}**" + (f"\nTags: {tags}" if tags else "")

    async def hackernews(self, topic: str = "top") -> str:
        topic = topic.strip().lower() or "top"
        if topic in {"top", "best", "new", "ask", "show", "job"}:
            ids = await self._get_json(f"https://hacker-news.firebaseio.com/v0/{topic}stories.json")
            label = topic
        else:
            search = await self._get_json(
                "https://hn.algolia.com/api/v1/search",
                params={"query": topic, "tags": "story", "hitsPerPage": 5},
            )
            hits = search.get("hits") if isinstance(search.get("hits"), list) else []
            lines = [f"**Hacker News — “{topic}”**"]
            for hit in hits[:5]:
                title = str(hit.get("title") or "Untitled")
                points = hit.get("points") or 0
                url = str(hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}")
                lines.append(f"• **{title}** ({points} pts)\n  {url}")
            return "\n".join(lines)[:3500]
        story_ids = ids[:5] if isinstance(ids, list) else []
        lines = [f"**Hacker News — {label} stories**"]
        for story_id in story_ids:
            item = await self._get_json(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
            title = str(item.get("title") or "Untitled")
            score = item.get("score") or 0
            url = str(item.get("url") or f"https://news.ycombinator.com/item?id={story_id}")
            lines.append(f"• **{title}** ({score} pts)\n  {url}")
        return "\n".join(lines)[:3500]

    async def shorten_url(self, url: str) -> str:
        """Shorten a URL with multi-provider fallback (is.gd → v.gd → tinyurl)."""
        url = (url or "").strip()[:2000]
        if not re.match(r"^https?://", url, re.I):
            raise FreeToolsError("Provide a valid http(s) URL to shorten.")
        errors: list[str] = []

        try:
            data = await self._get_json("https://is.gd/create.php", params={"format": "json", "url": url})
            short = str(data.get("shorturl") or "").strip()
            if short.startswith("http"):
                return f"**Short link**\n{short}\n\nOriginal: {url}\nProvider: is.gd"
            errors.append(str(data.get("errormessage") or "is.gd returned empty"))
        except Exception as exc:
            errors.append(f"is.gd: {exc}")

        try:
            data = await self._get_json("https://v.gd/create.php", params={"format": "json", "url": url})
            short = str(data.get("shorturl") or "").strip()
            if short.startswith("http"):
                return f"**Short link**\n{short}\n\nOriginal: {url}\nProvider: v.gd"
            errors.append(str(data.get("errormessage") or "v.gd returned empty"))
        except Exception as exc:
            errors.append(f"v.gd: {exc}")

        try:
            text = await self._get_text("https://tinyurl.com/api-create.php", params={"url": url})
            short = (text or "").strip()
            if short.startswith("http"):
                return f"**Short link**\n{short}\n\nOriginal: {url}\nProvider: tinyurl"
            errors.append("tinyurl returned empty")
        except Exception as exc:
            errors.append(f"tinyurl: {exc}")

        raise FreeToolsError("Could not shorten that URL. " + "; ".join(errors[:3]))

    async def random_fact(self) -> str:
        data = await self._get_json("https://uselessfacts.jsph.pl/api/v2/facts/random")
        fact = str(data.get("text") or data.get("data") or "").strip()
        if not fact:
            raise FreeToolsError("No fact was returned.")
        return f"**Did you know?**\n{fact}"

    async def translate(self, text: str, target: str, source: str = "auto") -> str:
        text = text.strip()[:800]
        target = target.strip().lower()[:5] or "en"
        source = "auto" if source == "auto" else source.strip().lower()[:5]
        if not text:
            raise FreeToolsError("Provide text to translate.")
        pair = f"{source}|{target}" if source != "auto" else f"auto|{target}"
        data = await self._get_json(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": pair},
        )
        response = data.get("responseData") if isinstance(data.get("responseData"), dict) else {}
        translated = str(response.get("translatedText") or "").strip()
        if not translated:
            raise FreeToolsError("Translation failed.")
        return f"**Translation → {target}**\n{translated}\n\n_Original:_ {text[:400]}"

    async def dad_joke(self) -> str:
        data = await self._get_json("https://icanhazdadjoke.com/", headers={"Accept": "application/json"})
        joke = str(data.get("joke") or "").strip()
        if not joke:
            raise FreeToolsError("No joke was returned.")
        return f"**Dad joke**\n{joke}"

    async def number_fact(self, number: str) -> str:
        number = re.sub(r"\D", "", number.strip())[:12]
        if not number:
            raise FreeToolsError("Provide a number for the fact lookup.")
        data = await self._get_json(f"http://numbersapi.com/{number}?json")
        text = str(data.get("text") or "").strip()
        if not text:
            raise FreeToolsError(f"No fact found for {number}.")
        return f"**Number fact — {number}**\n{text}"

    async def ip_lookup(self, ip: str) -> str:
        ip = ip.strip()[:45]
        if not re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", ip):
            raise FreeToolsError("Provide a valid IPv4 address.")
        data = await self._get_json(f"http://ip-api.com/json/{quote(ip)}", params={"fields": "status,message,country,regionName,city,isp,org,timezone,lat,lon,query"})
        if data.get("status") != "success":
            raise FreeToolsError(str(data.get("message") or "IP lookup failed."))
        return (
            f"**IP lookup — {data.get('query', ip)}**\n"
            f"Location: {data.get('city', '')}, {data.get('regionName', '')}, {data.get('country', '')}\n"
            f"ISP: {data.get('isp', 'n/a')} · Org: {data.get('org', 'n/a')}\n"
            f"Timezone: {data.get('timezone', 'n/a')} · Coords: {data.get('lat')}, {data.get('lon')}"
        )

    async def qr_code(self, data: str) -> str:
        data = data.strip()[:1000]
        if not data:
            raise FreeToolsError("Provide text or a URL to encode as a QR code.")
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(data)}"
        return f"**QR code**\nScan or open:\n{url}\n\n_Encoded:_ {data[:200]}"

    async def nasa_apod(self) -> str:
        payload = await self._get_json(
            "https://api.nasa.gov/planetary/apod",
            params={"api_key": "DEMO_KEY"},
        )
        title = str(payload.get("title") or "Astronomy Picture of the Day")
        explanation = str(payload.get("explanation") or "")[:900]
        media = str(payload.get("url") or payload.get("hdurl") or "")
        date = str(payload.get("date") or "")
        copyright_line = str(payload.get("copyright") or "")
        lines = [f"**NASA APOD — {title}**", f"Date: {date}"]
        if media:
            lines.append(media)
        if explanation:
            lines.append(explanation)
        if copyright_line:
            lines.append(f"© {copyright_line}")
        return "\n\n".join(lines)[:3500]

    async def cat_fact(self) -> str:
        data = await self._get_json("https://catfact.ninja/fact")
        fact = str(data.get("fact") or "").strip()
        if not fact:
            raise FreeToolsError("No cat fact was returned.")
        return f"**Cat fact**\n{fact}"

    async def country_info(self, country: str) -> str:
        country = country.strip()[:80]
        if not country:
            raise FreeToolsError("Provide a country name.")
        data = await self._get_json(f"https://restcountries.com/v3.1/name/{quote(country)}", params={"fields": "name,capital,region,subregion,population,timezones,currencies,languages,flags"})
        if not isinstance(data, list) or not data:
            raise FreeToolsError(f"No country matched “{country}”.")
        entry = data[0]
        name = (entry.get("name") or {}).get("common") or country
        capital = ", ".join(entry.get("capital") or []) or "n/a"
        region = f"{entry.get('region', '')} / {entry.get('subregion', '')}".strip(" /")
        population = entry.get("population")
        timezones = ", ".join(entry.get("timezones") or [])[:120]
        currencies = ", ".join(f"{code} ({(info or {}).get('name', '')})" for code, info in (entry.get("currencies") or {}).items()) or "n/a"
        languages = ", ".join((entry.get("languages") or {}).values()) or "n/a"
        flag = (entry.get("flags") or {}).get("png") or ""
        pop_text = f"{population:,}" if isinstance(population, int) else "n/a"
        lines = [
            f"**{name}**",
            f"Capital: {capital} · Region: {region}",
            f"Population: {pop_text}",
            f"Languages: {languages}",
            f"Currencies: {currencies}",
            f"Timezones: {timezones}",
        ]
        if flag:
            lines.append(flag)
        return "\n".join(lines)[:3500]

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"name": "weather", "summary": "Live weather via Open-Meteo", "example": "Lily weather in Tokyo"},
            {"name": "crypto", "summary": "Crypto prices via CoinGecko", "example": "Lily bitcoin price"},
            {"name": "exchange", "summary": "FX rates via Frankfurter", "example": "Lily convert 100 USD to EUR"},
            {"name": "wikipedia", "summary": "Wikipedia summaries", "example": "Lily wiki Python programming"},
            {"name": "dictionary", "summary": "English definitions", "example": "Lily define serendipity"},
            {"name": "anime", "summary": "Anime search via Jikan", "example": "Lily anime search Frieren"},
            {"name": "github", "summary": "Public GitHub repo stats", "example": "Lily github torvalds/linux"},
            {"name": "worldtime", "summary": "World clocks via WorldTimeAPI", "example": "Lily time in London"},
            {"name": "quote", "summary": "Inspirational quotes", "example": "Lily daily quote"},
            {"name": "hackernews", "summary": "HN top/search stories", "example": "Lily hacker news top"},
            {"name": "shorten", "summary": "URL shortener via is.gd", "example": "Lily shorten https://example.com"},
            {"name": "fact", "summary": "Random facts", "example": "Lily random fact"},
            {"name": "translate", "summary": "Free translation via MyMemory", "example": "Lily translate hello to Spanish"},
            {"name": "joke", "summary": "Dad jokes via icanhazdadjoke", "example": "Lily tell me a joke"},
            {"name": "number", "summary": "Number trivia via Numbers API", "example": "Lily number fact 42"},
            {"name": "ip", "summary": "IPv4 geolocation via ip-api", "example": "Lily ip lookup 8.8.8.8"},
            {"name": "qr", "summary": "QR code image links", "example": "Lily qr code for https://example.com"},
            {"name": "nasa", "summary": "NASA astronomy picture of the day", "example": "Lily nasa apod"},
            {"name": "cat", "summary": "Random cat facts", "example": "Lily cat fact"},
            {"name": "country", "summary": "Country profiles via REST Countries", "example": "Lily country info Japan"},
        ]


_WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Rain", 65: "Heavy rain", 71: "Slight snow", 73: "Snow", 75: "Heavy snow",
    80: "Rain showers", 81: "Moderate showers", 82: "Violent showers", 95: "Thunderstorm",
}


free_tools = FreeTools()
