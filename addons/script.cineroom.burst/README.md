# Cineroom Burst v2.0

Biblioteca de scrapers profissional para addons de streaming do Kodi.

## Provedores Suportados

- **Stremio**: Brazuca, Torrentio, SkyFlix, CDFlix, Mico-Leão
- **AnimeZey**: Conteúdo de anime especializado
- **Comando Top**: Filmes e séries
- **Apache Torrent**: Links torrent
- **Starck Filmes**: Streaming direto
- **Filmes Master**: Biblioteca de conteúdo
- **CMD1**: Provedor alternativo

## Uso

```python
import script.cineroom.burst as burst

provider_data = {
    "url": "https://brazuca.life",
    "configurable": False,
    "priority": 1
}

item_data = {
    "imdb_id": "tt1234567",
    "media_type": "movie",
    "title": "Nome do Filme"
}

sources = burst.scrape("Brazuca", provider_data, item_data)
```

## Instalação

Instale via arquivo ZIP no Kodi.

## Licença

GPL-3.0

## Autor

Gael - 2026
