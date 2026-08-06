# Hello My Assistant

**Hello My Assistant**는 사용자의 복잡한 작업을 자율적으로 판단하고 대신 처리해 주는 지능형 AI 어시스턴트 서비스입니다.

## 프로젝트 동기

이 프로젝트는 사용자에게 제공되는 **AI 서비스(Service)의 기반 아키텍처**와, 그 내부에서 동작하는 **AI 에이전트(Agent)의 오케스트레이션 과정**을 분리하여 깊이 이해하기 위해 시작했습니다.

이를 위해 **백엔드 아키텍처 설계**부터 **에이전트의 핵심 요소(Tools, Memory 등) 통합**까지 포괄적으로 다루고 있습니다. 이 두 계층(Service와 Agent)을 연결하며 마주하는 문제들을 직접 해결해 나감으로써, **시스템의 전체 동작 원리를 완벽히 이해하고, 정밀한 관측(Observability)을 통해 병목과 원인을 파악하여 성능을 지속적으로 개선하는 것을 목표로 합니다.**

## 시스템 아키텍처

이 프로젝트는 현재 탄탄한 백엔드 인프라와 클린 아키텍처 기반(Foundation)을 완성한 상태입니다.

```mermaid
graph LR
    %% 스타일 정의
    classDef client fill:#f9f9f9,stroke:#333,stroke-width:2px,color:#333
    classDef http fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px,color:#0d47a1
    classDef agent fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#1b5e20
    classDef ext fill:#fff3e0,stroke:#fb8c00,stroke-width:2px,color:#e65100

    Client((사용자)):::client

    subgraph Service_Layer [서비스 계층 : 정책 및 통신]
        API[FastAPI & Assistant<br>오류 통제 및 SSE 응답]:::http
    end

    subgraph Agent_Layer [에이전트 계층 : 지능]
        Agent[Pydantic AI<br>사고 및 추론]:::agent
    end

    LLM((LLM API)):::ext

    %% 상호작용 및 데이터 흐름
    Client -->|1. 채팅 요청| API
  
    API <-->|2. 컨텍스트 전달 및 청크 반환| Agent
    Agent <-->|3. 프롬프트 및 응답| LLM
  
    API -.->|4. AssistantEvent (SSE)| Client
```

**1. 엄격한 계층 분리 (Strict Layer Separation)**

* **설계 결정**: HTTP 요청을 처리하는 `서비스 계층(FastAPI, Assistant)`과 실제 AI의 판단 로직을 담당하는 `에이전트 계층(Pydantic AI)`을 완전히 분리했습니다.
* **이유**: 향후 터미널(CLI), WebSocket, 외부 메신저 등 새로운 인터페이스가 추가되더라도 핵심 에이전트 로직은 단 한 줄도 수정할 필요가 없는 높은 확장성을 보장하기 위함입니다.

**2. 단방향 상태 제어와 이벤트 통신 (Event-Driven Contract)**

* **설계 결정**: 서비스 계층(`Assistant`)은 에이전트의 내부 실행 결과나 예외를 클라이언트에게 직접 노출하지 않고, `AssistantEvent`(Delta, Completed, Failed)라는 추상화된 애플리케이션 규약으로 변환하여 발행합니다.
* **이유**: 비결정론적인 외부 LLM에서 예기치 않은 오류가 발생하더라도, 서비스 계층이 이를 안전한 이벤트로 분류하여 제어함으로써 HTTP 계층이 프로토콜(SSE) 수준에서 시스템 중단 없이 안정적으로 응답을 처리할 수 있도록 설계했기 때문입니다.

**3. 계층별 엔드투엔드 관측성 (Layered Observability)**

* **설계 결정**: 단순한 텍스트 로그에 의존하지 않고, 서비스 계층과 에이전트 계층의 관측 지점을 분리하되 이를 하나의 트레이스(Trace)로 묶어(Logfire/OpenTelemetry) 전체 생명 주기를 계측합니다.
* **이유**: 각 계층의 책임에 맞는 독립적인 디버깅과 성능 최적화를 수행하기 위함입니다.
  * **서비스 계층 관측**: 스트리밍 생명주기(`chat.stream`), 연결 끊김, 최종 응답 상태(`chat.outcome`)를 추적합니다. 이를 통해 네트워크 장애와 애플리케이션 오류를 명확히 격리하고 API의 신뢰성(SLA)을 보장합니다.
  * **에이전트 계층 관측**: 모델로 전달되는 프롬프트, 도구 호출 순서, LLM 지연 시간 및 토큰 사용량을 추적합니다. 이를 통해 블랙박스인 AI의 논리적 추론 과정을 투명하게 디버깅하고, 응답 품질과 비용을 최적화하는 엔지니어링을 수행합니다.

## 저장소 구조

```text
hello-my-assistant
├── apps/
│   ├── api/      # 실제 서비스될 백엔드 애플리케이션 (FastAPI + Pydantic AI)
│   └── cli/      # API 환경을 로컬에서 테스트하기 위한 터미널 기반 클라이언트
├── docs/
│   ├── agents/   # AI 코딩 어시스턴트용 개발 워크플로우
│   └── design/   # 아키텍처 설계 결정안(ADR) 및 세부 컴포넌트 명세서
└── CONTEXT.md    # 개발자와 AI가 공통으로 준수해야 할 저장소 핵심 개발 규칙
```

## 시작하기

### 1. API 서버 실행 (`apps/api`)

#### 작업 디렉토리 이동

API 서버를 구동하기 위해 해당 디렉토리로 이동합니다.

```bash
cd apps/api
```

#### 환경 변수 설정

API 구동에 필요한 LLM 접근 키와 설정값을 환경 변수로 주입합니다.

```bash
cp .env.example .env
```

`.env` 파일을 열어 `LLM_API_KEY` 등의 필수 항목을 기입해 주세요.

#### 의존성 설치

`uv`를 사용하여 프로젝트에 필요한 의존성 패키지들을 동기화(설치)합니다.

```bash
uv sync
```

#### API 서버 실행

FastAPI 서버를 개발(Dev) 모드로 실행합니다.

```bash
uv run fastapi dev src/hello_my_assistant_api/main.py
```

서버가 정상적으로 실행되면 `http://localhost:8000`에서 대기합니다.

### 2. CLI 클라이언트 실행 (`apps/cli`)

#### 작업 디렉토리 이동

새로운 터미널을 열고, 프로젝트 루트 경로에서 CLI 디렉토리로 이동합니다.

```bash
cd apps/cli
```

#### 의존성 설치

CLI 역시 별도의 환경을 가지므로 의존성을 설치해야 합니다.

```bash
uv sync
```

#### 클라이언트 실행

터미널에서 에이전트와 대화하기 위해 애플리케이션을 구동합니다. (API 서버가 실행 중이어야 합니다.)

```bash
uv run python -m hello_my_assistant_cli.main
```
