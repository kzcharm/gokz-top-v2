# Translation Guidelines

- Last Updated: 2026-05-09
- Applies to: `frontend/` i18n work

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
  - `Steam ID64`
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
