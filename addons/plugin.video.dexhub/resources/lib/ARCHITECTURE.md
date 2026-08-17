# Dex Hub staged modular architecture

Version 3.9.250 introduces stable module boundaries without changing Kodi URLs.
The legacy clients remain proven backends while plugin.py now imports provider,
search, playback and subtitle facades. Future moves can relocate implementation
behind these interfaces without touching TMDb Helper or skin integrations.


## 3.9.251 Nuvio/Stremio interoperability
- integrations/nuvio_sync.py owns portable addon + collection import/export.
- search/coordinator.py yields fast providers first and never waits past deadline.
- Kaptain/Nuvio folders/catalogSources are normalized through collection_sets.py.

## 3.9.267 Nuvio sectioned sync
- Add-ons, collections, and watch progress sync independently.
- Collection pull results are written back through collection_sets.import_sets.
- Partial failures no longer hide successful sections.

## 3.9.270 adaptive source scheduler
`search/provider_stats.py` keeps a privacy-safe rolling latency/success index and
orders provider tasks per device. It stores no titles, ids, URLs, tokens or
history. Every enabled provider is still queried; only launch order changes.


## 3.9.272 — Unified home-server layer

- `identity/media.py` owns stable IMDb/TMDb/TVDb + episode identity.
- `servers/base.py` defines the Plex/Emby/Jellyfin provider contract.
- `servers/plex.py` and `servers/emby.py` adapt the proven clients.
- `servers/health.py` orders servers by real local latency/success and applies only temporary cooldowns.
- `search/candidates.py` defines provider-neutral stream candidates.
- `plugin.py` now routes native source execution through the health layer while keeping all public Kodi/TMDb Helper actions compatible.


## 3.9.273
- Account/sync dialogs moved to `routes/accounts.py`.
- Hot routes use `routes/fast_dispatch.py` with legacy fallback.
- `servers/registry.py` provides lazy unified Plex/Emby server jobs.
- Native clients are not imported while browsing Stremio-only pages.
