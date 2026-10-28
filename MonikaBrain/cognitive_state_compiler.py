# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attention_arbiter import AttentionArbiter, AttentionDecision
from audience_model import AudienceModel, AudienceSnapshot
from event_bus import EventBus, NormalizedEvent
from memory_policy import MemoryContext, MemoryReadPolicy
from people_model import PeopleModel, PersonSnapshot
from salience_engine import SalienceEngine, SalienceSnapshot
from self_model import SelfModel, SelfSnapshot
from signal_extractor import ExtractedSignals, SignalExtractor
from situation_model import SituationModel, SituationSnapshot
from cognitive_lifecycle import ConversationGoalManager, GoalSnapshot, SceneStoryManager, StorySnapshot, TopicLifecycle, TopicStatus
from cognitive_personality import (
    AutobiographicalTimeline,
    HumanFeedbackLoop,
    IdentityBoundary,
    IdentityBoundaryPolicy,
    PersonaEvolution,
    PersonaEvolutionPolicy,
    RelationshipDepth,
    RelationshipDepthModel,
    SelfReflectionDigest,
    UncertaintyBehavior,
    UncertaintyProfile,
)


@dataclass
class CognitiveState:
    event: NormalizedEvent
    signals: ExtractedSignals
    attention: AttentionDecision
    situation: SituationSnapshot
    current_person: PersonSnapshot
    known_people: list[PersonSnapshot]
    audience: AudienceSnapshot
    self_snapshot: SelfSnapshot
    memory: MemoryContext
    salience: SalienceSnapshot
    goal: GoalSnapshot
    topic_status: TopicStatus
    story: StorySnapshot
    relationship_depth: RelationshipDepth
    persona_evolution: PersonaEvolution
    uncertainty: UncertaintyProfile
    identity_boundary: IdentityBoundary
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.__dict__,
            "signals": self.signals.__dict__,
            "attention": self.attention.__dict__,
            "situation": self.situation.__dict__,
            "current_person": self.current_person.__dict__,
            "known_people": [p.__dict__ for p in self.known_people[:8]],
            "audience": self.audience.__dict__,
            "self": self.self_snapshot.__dict__,
            "memory": self.memory.__dict__,
            "salience": [item.__dict__ for item in self.salience.items],
            "goal": self.goal.__dict__,
            "topic_status": self.topic_status.__dict__,
            "story": self.story.__dict__,
            "relationship_depth": self.relationship_depth.__dict__,
            "persona_evolution": self.persona_evolution.__dict__,
            "uncertainty": self.uncertainty.__dict__,
            "identity_boundary": self.identity_boundary.__dict__,
            "constraints": self.constraints,
        }

    def prompt_block(self) -> str:
        parts = [
            "[COGNITIVE STATE]",
            f"- source={self.event.source}, role={self.event.role}, speaker={self.event.display_name}.",
            f"- intent={self.signals.intent}, topic={self.signals.topic or 'none'}, memory_intent={self.signals.memory_intent}.",
            f"- goal={self.goal.goal}, topic_status={self.topic_status.status}, uncertainty={self.uncertainty.level}.",
            f"- attention={self.attention.focus}, reply={self.attention.should_reply}, reason={self.attention.reason}.",
            f"- situation={self.situation.mode}, pace={self.situation.pace}, tension={self.situation.tension:.2f}.",
        ]
        parts.extend(f"- constraint: {x}" for x in self.constraints)
        return "\n".join(parts)


class CognitiveStateCompiler:
    """Главный арбитр: собирает мозг Моники в один prompt-state."""

    def __init__(self, conn, social_memory=None, creator_id: str = "Duncan", debug_trace=None):
        self.event_bus = EventBus()
        self.signal_extractor = SignalExtractor()
        self.attention_arbiter = AttentionArbiter()
        self.situation_model = SituationModel()
        self.people_model = PeopleModel(conn, social_memory=social_memory, creator_id=creator_id)
        self.audience_model = AudienceModel()
        self.self_model = SelfModel()
        self.memory_read_policy = MemoryReadPolicy()
        self.salience_engine = SalienceEngine()
        self.goal_manager = ConversationGoalManager()
        self.topic_lifecycle = TopicLifecycle()
        self.story_manager = SceneStoryManager()
        self.relationship_depth_model = RelationshipDepthModel()
        self.persona_evolution_policy = PersonaEvolutionPolicy()
        self.uncertainty_behavior = UncertaintyBehavior()
        self.identity_boundary_policy = IdentityBoundaryPolicy()
        self.feedback_loop = HumanFeedbackLoop()
        self.timeline = AutobiographicalTimeline()
        self.reflection_digest = SelfReflectionDigest()
        self.debug_trace = debug_trace

    def compile(
        self,
        *,
        source: str,
        user_text: str,
        person_id: str,
        display_name: str,
        role: str,
        priority: int = 50,
        metadata: dict[str, Any] | None = None,
        scene_state: dict[str, Any] | None = None,
        relationship_state: dict[str, Any] | None = None,
        memory_facts: list[str] | None = None,
        active_desires: list[dict[str, Any]] | None = None,
        active_opinions: list[dict[str, Any]] | None = None,
    ) -> CognitiveState:
        event = self.event_bus.publish(NormalizedEvent(
            source=source or "dialogue",
            text=user_text or "",
            person_id=str(person_id or ""),
            display_name=str(display_name or person_id or ""),
            role=role or "viewer",
            priority=int(priority or 50),
            metadata=metadata or {},
        ))
        signals = self.signal_extractor.extract(event)
        source_counts = self.event_bus.source_counts(60.0)
        goal = self.goal_manager.detect(event, signals, scene_state)
        topic_status = self.topic_lifecycle.update(scene_state, signals, user_text)
        story = self.story_manager.update(scene_state, event, signals)
        attention = self.attention_arbiter.decide(event, signals, load=source_counts)
        situation = self.situation_model.update(scene_state, event, signals, source_counts)
        memory = self.memory_read_policy.decide(signals, memory_facts or [], topic=situation.topic)
        current_person = self.people_model.current_person(person_id, display_name, role, relationship_state)
        known_people = self.people_model.known_people(limit=12) if memory.include_people or signals.mentions_people else []
        relationship_depth = self.relationship_depth_model.build(current_person)
        audience = self.audience_model.build(self.event_bus.recent(60))
        self_snapshot = self.self_model.build(active_desires, active_opinions)
        feedback = self.feedback_loop.observe(user_text or "")
        persona_evolution = self.persona_evolution_policy.build(active_desires, active_opinions, feedback)
        uncertainty = self.uncertainty_behavior.build(memory.confidence, goal.goal)
        identity_boundary = self.identity_boundary_policy.inspect_input(user_text or "")
        salience = self.salience_engine.rank(event, signals, memory.facts, known_people, active_desires or [])
        constraints = self._constraints(event, signals, attention, situation, memory)
        constraints.extend(topic_status.notes)
        constraints.extend(identity_boundary.constraints)
        state = CognitiveState(
            event=event,
            signals=signals,
            attention=attention,
            situation=situation,
            current_person=current_person,
            known_people=known_people,
            audience=audience,
            self_snapshot=self_snapshot,
            memory=memory,
            salience=salience,
            goal=goal,
            topic_status=topic_status,
            story=story,
            relationship_depth=relationship_depth,
            persona_evolution=persona_evolution,
            uncertainty=uncertainty,
            identity_boundary=identity_boundary,
            constraints=constraints,
        )
        if self.debug_trace:
            self.debug_trace.record("cognitive_state", state.to_dict())
        return state

    def prompt_block(self, state: CognitiveState) -> str:
        parts = [
            state.prompt_block(),
            self.self_model.prompt_block(state.self_snapshot),
            self.people_model.prompt_block(state.current_person, state.known_people, state.memory.include_people),
            self._relationship_block(state.relationship_depth),
            self.memory_read_policy.prompt_block(state.memory),
            self.salience_engine.prompt_block(state.salience),
            self._goal_block(state),
            self.story_manager.prompt_block(state.story),
            self._persona_evolution_block(state.persona_evolution),
            self._audience_block(state.audience),
            self.timeline.prompt_block(),
        ]
        if state.situation.notes:
            parts.append("[SITUATION NOTES]\n" + "\n".join(f"- {x}" for x in state.situation.notes))
        return "\n\n".join(part for part in parts if part)

    def _audience_block(self, audience: AudienceSnapshot) -> str:
        return (
            "[AUDIENCE MODEL]\n"
            f"- mood={audience.mood}, load={audience.load}, chat_messages={audience.chat_messages}, "
            f"toxic_pressure={audience.toxic_pressure:.2f}."
        )

    def _goal_block(self, state: CognitiveState) -> str:
        return (
            "[CONVERSATION CONTROL]\n"
            f"- goal={state.goal.goal}, confidence={state.goal.confidence:.2f}, reason={state.goal.reason}.\n"
            f"- topic={state.topic_status.topic or 'none'}, status={state.topic_status.status}, turns_left={state.topic_status.turns_left}.\n"
            f"- uncertainty={state.uncertainty.level}: {state.uncertainty.instruction}\n"
            f"- identity_boundary={state.identity_boundary.risk}."
        )

    def _relationship_block(self, depth: RelationshipDepth) -> str:
        return (
            "[RELATIONSHIP DEPTH]\n"
            f"- label={depth.label}, stance={depth.stance}, trust={depth.trust:.2f}, friction={depth.friction:.2f}."
        )

    def _persona_evolution_block(self, evolution: PersonaEvolution) -> str:
        if not evolution.notes:
            return ""
        return "[PERSONA EVOLUTION]\n" + "\n".join(f"- {note}" for note in evolution.notes)

    def observe_turn(self, user_text: str, reply: str, state: CognitiveState | None = None) -> None:
        if not state:
            return
        self.timeline.observe(user_text, reply, state.goal.goal)
        if self.debug_trace:
            self.debug_trace.record("autobiographical_timeline", {
                "moments": [m.__dict__ for m in self.timeline.moments[-5:]],
            })

    def _constraints(
        self,
        event: NormalizedEvent,
        signals: ExtractedSignals,
        attention: AttentionDecision,
        situation: SituationSnapshot,
        memory: MemoryContext,
    ) -> list[str]:
        constraints = [
            "LLM формулирует речь; факты, люди и сцена берутся из cognitive state.",
            "Если данных нет или confidence low, не выдумывать.",
            "Schema ownership: факты принадлежат MemoryPolicy/MemoryCore; люди принадлежат PeopleModel/SocialLayer; сцена принадлежит SituationModel; форма ответа принадлежит ResponsePolicy.",
            "Persona задаёт голос и характер, но не имеет права менять факты, людей, безопасность или сценический фокус.",
        ]
        if memory.include_people:
            constraints.append("На вопросы о людях отвечать из People Model, не из фантазии.")
        if situation.mode == "story":
            constraints.append("Удерживать текущую story-сцену несколько ходов.")
        if event.source == "donation":
            constraints.append("Донат изолирован: благодарить текущего донатера и не смешивать с прошлым чатом.")
        if attention.focus == "chat_noise":
            constraints.append("Можно не отвечать на шум чата.")
        if signals.toxicity > 0.5:
            constraints.append("Сохранять характер, но не разгонять токсичность.")
        return constraints
