# API Architecture

## Purpose

`apps/api`는 사용자의 단일 텍스트 요청을 받아 Assistant 응답을 SSE로
스트리밍하는 HTTP 애플리케이션이다. 이 문서는 현재 모듈의 책임, 의존성 방향,
외부 계약과 확장 기준을 설명한다.

현재 구조의 목표는 예측한 기능을 위한 계층을 미리 만드는 것이 아니라, 이미
존재하는 정책과 전송 복잡성을 작은 인터페이스 뒤에 모으는 것이다.

## Terminology

- **Assistant**는 사용자가 요청하고 응답받는 제품 전체를 나타내는 용어다.
- **Agent**는 Assistant 내부에서 모델 실행을 담당하는 AI 실행 주체다.
- **Assistant event**는 Assistant의 실행 결과를 전송 기술과 무관하게 표현한다.
- **HTTP/SSE adapter**는 HTTP 요청과 Assistant event를 외부 프로토콜로
  변환한다.

저장소 전체의 용어 결정은 [`CONTEXT.md`](../../CONTEXT.md)를 따른다.

## Module Responsibilities

| 모듈 | 책임 |
| --- | --- |
| `main.py` | 설정, Pydantic AI Agent, Assistant와 FastAPI 앱을 생성하는 composition root |
| `app.py` | 주입받은 Assistant로 FastAPI 앱을 조립하고 관측 및 라우터를 연결하는 app factory |
| `chat_http.py` | `/chat` 요청을 검증하고 Assistant 호출을 HTTP 응답 adapter에 연결 |
| `assistant.py` | 응답 제한 시간, 유효 출력 판정, 오류 정규화와 종료 event를 포함하는 애플리케이션 정책 |
| `agent.py` | 설정으로 모델 provider와 Pydantic AI Agent를 생성하는 framework adapter |
| `_chat_streaming_response.py` | Assistant event를 SSE로 인코딩하고 실제 응답 전송 및 `chat.stream` 관측 생명주기를 관리 |
| `observability.py` | FastAPI와 Pydantic AI 자동 계측을 fail-open 방식으로 초기화 |
| `settings.py` | 환경 변수에서 런타임 설정을 읽고 검증 |

`_chat_streaming_response.py`는 HTTP adapter의 private implementation이다. 다른
모듈은 이 파일의 내부 상태나 SSE 인코딩 함수에 의존하지 않는다.

## Dependency Direction

```text
main
├── settings
├── agent ───────────────> Pydantic AI / model provider
├── assistant ───────────> Pydantic AI Agent
└── app
    ├── observability ───> Logfire
    └── chat_http
        ├── assistant
        └── _chat_streaming_response
            └── assistant events
```

의존성은 composition root에서 구체적인 구현으로 향한다. `Assistant`는 FastAPI,
HTTP 또는 SSE를 알지 않으며, HTTP adapter는 Pydantic AI의 실행 결과나 예외를
직접 해석하지 않는다.

현재 `Assistant`가 Pydantic AI `Agent`를 직접 받는 것은 의도적인 선택이다.
Agent 구현이 하나뿐인 현재 별도의 port를 만들면 실제로 교체되는 대상 없이
인터페이스만 늘어난다. 두 번째 구현이나 테스트 seam에 대한 구체적인 요구가
생길 때 분리를 다시 검토한다.

## Request and Streaming Flow

```text
POST /chat
    │
    ▼
ChatRequest validation
    │ stripped, nonblank content
    ▼
Assistant.respond(content)
    │
    ▼
Pydantic AI Agent.run_stream(content)
    │ model text chunks
    ▼
AssistantEvent stream
    │
    ▼
ChatStreamingResponse
    │ SSE encoding and transmission
    ▼
HTTP client
```

`Assistant.respond()`는 하나의 작은 인터페이스 뒤에 모델 스트리밍, 제한 시간,
출력 유효성 검사와 예외 분류를 숨긴다. 호출자는 Pydantic AI 예외나 모델별
결과를 알 필요 없이 `AssistantEvent`만 처리한다.

`ChatStreamingResponse`는 event를 SSE로 변환하는 것뿐 아니라 실제 ASGI 응답
전송이 끝날 때까지 스트림의 생명주기를 소유한다. 따라서 정상 완료, 애플리케이션
오류와 클라이언트 중단을 서로 다른 결과로 관측할 수 있다.

## Application Event Contract

`Assistant.respond(content)`는 다음 event를 순서대로 내보낸다.

| event | 의미 |
| --- | --- |
| `AssistantDelta(content)` | 모델이 생성한 텍스트 조각 |
| `AssistantCompleted()` | 하나 이상의 비공백 결과를 생성하고 정상 완료 |
| `AssistantFailed(kind)` | 안전하게 분류된 실패로 종료 |

현재 Assistant implementation은 0개 이상의 delta 뒤에 정확히 하나의 completed
또는 failed terminal event를 내보낸다. 빈 문자열 chunk는 생략하지만 공백 chunk는
전송할 수 있으며, 전체 결과가 공백뿐이면 `invalid_response`로 종료한다.

실패 분류는 provider 예외를 외부 adapter에 노출하지 않는 안정적인 계약이다.

| failure kind | 조건 |
| --- | --- |
| `invalid_response` | 빈 결과, 공백뿐인 결과 또는 예상하지 못한 모델 동작 |
| `model_error` | 모델 API 호출 실패 |
| `timeout` | 설정된 응답 제한 시간 초과 |
| `internal_error` | 그 밖의 처리되지 않은 Assistant 실행 오류 |

## HTTP and SSE Contract

`POST /chat`은 다음 JSON 요청을 받는다.

```json
{"content":"사용자 요청"}
```

`content`는 양쪽 공백을 제거한 뒤 비어 있으면 HTTP 422로 거부된다. 유효한
요청은 `text/event-stream` 응답과 다음 header를 사용한다.

```text
Cache-Control: no-cache
X-Accel-Buffering: no
```

Assistant event는 다음 SSE event로 변환된다.

| Assistant event | SSE event | data |
| --- | --- | --- |
| `AssistantDelta` | `delta` | `{"content":"..."}` |
| `AssistantCompleted` | `done` | `{}` |
| `AssistantFailed` | `error` | 안전한 `code`와 `message` |

스트리밍이 시작된 뒤 발생한 애플리케이션 실패는 HTTP 상태를 변경할 수 없으므로
HTTP 200 응답 안의 `error` event로 전달될 수 있다. 클라이언트는 HTTP 상태만이
아니라 terminal SSE event도 확인해야 한다.

## Observability

실제 `/chat` 요청의 trace 계층은 다음과 같다.

```text
HTTP POST /chat
└── chat.stream
    └── Agent
        └── Model
```

`chat.stream` span은 `ChatStreamingResponse`가 실제 응답을 전송하는 동안
유지된다. span에는 다음 저카디널리티 속성만 기록한다.

| 속성 | 조건 | 값 |
| --- | --- | --- |
| `chat.outcome` | 항상 | `done`, `error`, `incomplete` |
| `error.type` | `error`일 때만 | Assistant failure kind |
| `chat.time_to_first_delta_ms` | 첫 비공백 delta가 있을 때만 | 서버에서 관측한 경과 시간 |

- `done`은 `done` terminal event가 만들어진 상태다.
- `error`는 `error` terminal event 또는 예상하지 못한 전송 오류가 발생한
  상태다.
- `incomplete`는 terminal event 전에 연결 해제 또는 취소로 전송이 중단된
  상태다.

오류 outcome은 OpenTelemetry `ERROR` status를 갖는다. 취소와 연결 해제는
오류로 기록하지 않으며 원래 중단 신호를 호출자에게 다시 전달한다.

사용자 요청, 모델 응답, SSE delta 본문, 원본 예외 메시지와 traceback은
`chat.stream` 속성으로 수집하지 않는다. Pydantic AI 자동 계측도
`include_content=False`로 초기화한다. 관측 초기화 실패는 애플리케이션 시작을
막지 않는다.

## Extension Guidelines

새 모듈이나 seam은 이름만으로 미래 구조를 예고하기 위해 추가하지 않는다. 다음
조건 중 하나가 실제로 나타날 때 도입한다.

- 독립적으로 설명하고 검증해야 하는 정책이나 상태가 생긴다.
- 기존 인터페이스를 복잡하게 만들지 않고 숨겨야 할 구현 복잡성이 생긴다.
- 두 번째 adapter 또는 구현이 생겨 교체 가능한 seam이 필요하다.
- 관측된 실패나 제품 요구를 현재 구조로 해결하기 어렵다.

예를 들어 모델이 외부 정보를 조회하거나 행동해야 할 때 구체적인 tool을,
후속 요청에 이전 대화가 필요할 때 conversation history와 보존 정책을 추가한다.
재시도, 승인, 재개가 필요한 실행이 생길 때 명시적인 orchestration 상태를
도입한다. 그 전에는 빈 `tools`, `memory`, `orchestration` 계층을 만들지 않는다.

테스트는 private helper의 형태보다 각 모듈의 인터페이스와 외부에서 관찰되는
계약을 검증한다. HTTP 계약, Assistant 정책, SSE 변환과 관측 계약은 서로 다른
테스트에서 책임에 맞게 검증한다.
