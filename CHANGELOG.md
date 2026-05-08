# Changelog

## [0.2.1](https://github.com/tropicalennui/steampunk/compare/v0.2.0...v0.2.1) (2026-05-08)


### Bug Fixes

* **igdb:** correct API field rename and DuckDB FK merge issue ([1cc36c4](https://github.com/tropicalennui/steampunk/commit/1cc36c4ff359684aa6ac78cb8623fe01ff293c01))
* **igdb:** correct API field rename and DuckDB FK merge issue ([3ec0e2f](https://github.com/tropicalennui/steampunk/commit/3ec0e2fee7dba0ca1c2195c9c9938728e0c2ff6e))

## [0.2.0](https://github.com/tropicalennui/steampunk/compare/v0.1.0...v0.2.0) (2026-05-07)


### Features

* library grid/list view, column picker, and game merge ([a37439f](https://github.com/tropicalennui/steampunk/commit/a37439f5f641a1df63cdb1f75c2d9199ec91fd28))
* **library:** add grid/list toggle, column picker, and drag-to-merge ([0f3d640](https://github.com/tropicalennui/steampunk/commit/0f3d640bf606e9712dd7ecd136284cd8589530d1))
* **library:** prompt for preferred title on game merge ([161d6bd](https://github.com/tropicalennui/steampunk/commit/161d6bdf42404d3d58a1b29aaf4d62e6b8928506))
* **tests:** add automated test suite (US-017) ([0c20bfd](https://github.com/tropicalennui/steampunk/commit/0c20bfd7acb9771166cbf45f8e2cc29d62652c38))
* **tests:** automated test suite (US-017) ([95242bf](https://github.com/tropicalennui/steampunk/commit/95242bfd13ac055a6c4db6ba5a160b4a099b1055))
* **xbox:** add Xbox Live integration ([3dd1f7e](https://github.com/tropicalennui/steampunk/commit/3dd1f7e711da2372a934de2be6a41e41ade07fa7))
* **xbox:** add Xbox Live integration ([2afaa44](https://github.com/tropicalennui/steampunk/commit/2afaa44ffe07fa75b7d6141a839224723caee8a4))


### Bug Fixes

* **library:** fix merge transaction and add platform-specific card stats ([8b2889f](https://github.com/tropicalennui/steampunk/commit/8b2889fc21025cb13e3f3728cce2ef18fb3e7256))
* **lint:** address two SonarQube issues in main.py ([0c3aff2](https://github.com/tropicalennui/steampunk/commit/0c3aff2b787cd27abb0b060b24ea45e9dcf8795c))
* **main:** resolve type-checker errors in Xbox callback server ([7ac0e83](https://github.com/tropicalennui/steampunk/commit/7ac0e83d45719903564b240d0c39106916a916d3))
* **merge:** pre-fetch game rows before transaction, surface errors in UI ([d78f81d](https://github.com/tropicalennui/steampunk/commit/d78f81d72faa05daa780d036fc7cb056b0403ecc))
* **merge:** use merged_into column instead of re-pointing platform_games ([89eaecb](https://github.com/tropicalennui/steampunk/commit/89eaecb91e07725bd1b1f4f6286ecb384868b66c))
* **merge:** work around DuckDB FK cascade-check by nulling game_id first ([f03593d](https://github.com/tropicalennui/steampunk/commit/f03593dacf97d5661096ea625073ed0ffdd88ff6))
* **security:** don't expose exception details in merge error response ([332ae78](https://github.com/tropicalennui/steampunk/commit/332ae789eea7c2044c00e8459632f7158227ccf0))
* **security:** don't expose exception details in merge error response ([5a520fc](https://github.com/tropicalennui/steampunk/commit/5a520fc7c3e4757b2ebb7009a74118de4eb59229))


### Refactoring

* **library:** fix SonarQube issues in column registry and query builder ([06bf116](https://github.com/tropicalennui/steampunk/commit/06bf11658f369c7938f2b47f2425936d4eb189cb))
* **src:** split main.py and collect.py into focused modules (US-018) ([c09d8bd](https://github.com/tropicalennui/steampunk/commit/c09d8bddd93a87cb01d187f0c9f1ade6bfd213c6))
* **src:** split main.py and collect.py into focused modules (US-018) ([3de9c8e](https://github.com/tropicalennui/steampunk/commit/3de9c8e6751316bac05864db0ecba52de8f48134))
