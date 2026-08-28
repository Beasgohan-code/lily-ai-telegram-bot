# Free public API tools

Lily can call a curated set of **no-key** public APIs for instant lookups.

## Available tools

| Tool | Provider | Example |
|---|---|---|
| Weather | Open-Meteo | `Lily weather in Tokyo` |
| Crypto | CoinGecko | `Lily bitcoin price` |
| Exchange | Frankfurter | `Lily convert 100 USD to EUR` |
| Wikipedia | Wikipedia REST | `Lily wiki Python` |
| Dictionary | Free Dictionary API | `Lily define serendipity` |
| Anime | Jikan (MAL) | `Lily anime search Frieren` |
| GitHub | GitHub public API | `Lily github torvalds/linux` |
| World time | WorldTimeAPI | `Lily time in London` |
| Quote | Quotable | `Lily daily quote` |
| Hacker News | HN Firebase / Algolia | `Lily hacker news top` |
| Shorten URL | is.gd | `Lily shorten https://example.com` |
| Random fact | Useless Facts | `Lily random fact` |
| Translate | MyMemory | `Lily translate hello to Spanish` |
| Dad joke | icanhazdadjoke | `Lily tell me a joke` |
| Number fact | Numbers API | `Lily number fact 42` |
| IP lookup | ip-api | `Lily ip lookup 8.8.8.8` |
| QR code | QR Server | `Lily qr code for https://example.com` |
| NASA APOD | NASA Open API | `Lily nasa apod` |
| Cat fact | catfact.ninja | `Lily cat fact` |
| Country info | REST Countries | `Lily country info Japan` |

Say `Lily free tools` or `/tools` for the full catalog.

## Safety

- Results are bounded and attributed to their source.
- No credentials are stored or required.
- Disable with `LILY_ENABLE_FREE_TOOLS=false`.
