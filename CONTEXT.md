# Hello My Assistant

This context describes the user-facing AI assistant and the internal actor that carries out its requests.

## Language

**Assistant**:
The user-facing AI application that receives user requests and returns responses. It represents the service as experienced by users.
_Avoid_: Agent, chatbot, model

**Conversation**:
A sequence of Turns that share prior interaction context between the user and the Assistant.
_Avoid_: Chat, session, thread

**Turn**:
One interaction within a Conversation, beginning with a user request and ending when the Assistant completes or fails its response.
_Avoid_: Message, exchange

**Agent**:
An internal AI actor within the Assistant that uses a model and may use tools or contextual information to determine how to carry out a request.
_Avoid_: Assistant, service, model

**Tool**:
An individual operation that an Agent can request through a single invocation.
_Avoid_: Function, feature, capability

**Toolset**:
A collection of related Tools made available together to an Agent.
_Avoid_: Tool, capability
