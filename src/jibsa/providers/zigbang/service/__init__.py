"""직방 service: client 호출을 묶어 Listing 으로 정규화한다.

모듈은 CLI 명령 묶음 하나씩 맡는다 (docs/development/provider-conventions.md 'service 모듈을 나누는 기준',
docs/development/providers/zigbang.md '명령과 요청 흐름'). 기능마다 결과·조건 모델은 models, 함수는 functions(폴더 기능은 base·search·detail 같은 함수 모듈)에 둔다.
import 는 common(models → base → room·apt) → region → 기능 모듈(폴더 안은 models → base → search·detail) → listing 방향으로만 한다.
"""
