"""직방 service: client 호출을 묶어 Listing 으로 정규화한다.

모듈은 CLI 명령 묶음 하나씩 맡는다 (docs/development/provider-conventions.md 'service 모듈을 나누는 기준',
docs/development/providers/zigbang.md '명령과 요청 흐름'). 기능마다 상수는 constants, 결과·조건 모델은 models, 폴더 안 여러 파일이 같이 쓰는 함수는 common,
명령·주제 파일은 하는 일 이름(search·detail·info·listings·trend 같은 모듈, 명령 하나인 폴더는 명령 이름)에 둔다.
import 는 common(constants → models → 바닥 파일 → 주제 파일, 주제 파일끼리는 부르지 않는다) → region → 기능 모듈(폴더 안은 constants → models → common → 명령·주제 파일) → listing 방향으로만 한다.
"""
