# Translation Guidelines

- Last Updated: 2026-06-11
- Applies to: `frontend/` i18n work and public docs in `notes/docs/`

## Default Locale Policy
- English is the default locale and the source language for new UI copy.
- Supported locales:
  - `en`
  - `zh-CN`
  - `ru`
- Persist the selected language in local storage under `gokz-language`.
- On first load without a saved preference:
  - map `zh-*` to `zh-CN`
  - map `ru-*` to `ru`
  - map everything else to `en`

## Terminology Policy
- Preserve these terms in English. Do not translate them unless explicitly requested:
  - `Rating`
  - `Rating.E`
  - `Rating.H`
  - `GlobalAPI`
  - `Steam`
  - `SteamID64`
  - `NUB`
  - `PRO`
  - `OVR`
  - `KZT`
  - `SKZ`
  - `VNL`
- Preserve other obvious product and gameplay acronyms in English unless a future glossary explicitly overrides them.

## Style Guidance
- Prefer idiomatic native phrasing over literal translation.
- Keep UX copy concise and interface-appropriate.
- When a branded or technical term reads better in English inside a translated sentence, keep the term in English and localize the surrounding wording naturally.

## Public Documentation Parity
- Public docs live in the `notes/` submodule, with English pages under `notes/docs/` and translated pages under locale subdirectories such as `notes/docs/zh/`.
- Keep translated docs content-matched with English docs. A translated page should cover the same current content as its English counterpart, localized naturally rather than copied literally.
- When adding, deleting, renaming, shortening, or materially editing an English doc page, make the corresponding update to every available translated counterpart in the same task.
- When a user asks to delete or clean up documentation, apply that request across all language versions unless they explicitly scope the request to one language.
- Do not leave translated docs with stale sections, old links, or removed topic pages after English docs have been cleaned up.

## Confirmed UI Label Preferences
- Preferred Simplified Chinese mappings confirmed by the user:
  - `Map` -> `地图`
  - `Mode` -> `模式`
  - `Tier` -> `难度`
  - `TPs` -> `TPs`
  - `Time` -> `用时`
  - `Points` -> `分数`
  - `Server` -> `服务器`
  - `Datetime` -> `日期`
  - `Home` -> `主页`
  - `Records` -> `记录`
  - `Unfinished` -> `未完成`
  - `Stats` -> `数据`
  - `Strafe` -> `加速`
  - `Slide` -> `滑坡`
  - `Micro` stays `Micro`
  - Profile progression-bar `avg` stays `avg`

## Error Localization Scope
- Localize frontend-owned UI copy, labels, placeholders, empty states, toasts, dialogs, and generic error wrappers.
- Do not translate raw backend error detail strings in the frontend unless they are explicitly mapped to a frontend-owned message.
