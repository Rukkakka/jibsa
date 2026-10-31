"""직방 service: client 호출을 묶어 Listing 으로 정규화한다.

모듈은 CLI 명령 묶음 하나씩 맡는다 (docs/development/provider-conventions.md 'service 모듈을 나누는 기준',
docs/development/providers/zigbang.md '명령과 요청 흐름'). import 는 common → region → 기능 모듈 → detail 방향으로만 한다.
"""
