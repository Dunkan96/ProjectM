# stimulus.py
from dataclasses import dataclass, field
from typing import Optional, Any

@dataclass(order=True)
class Stimulus:
    """Стимул для обработки Моникой."""
    priority: int
    source: str = field(compare=False)
    content: str = field(compare=False)
    timestamp: float = field(compare=False, default_factory=lambda: __import__('time').time())
    metadata: Optional[dict] = field(compare=False, default=None)
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    @classmethod
    def create_voice(cls, text: str, priority: int = 100):
        return cls(source="voice", content=text, priority=priority)
    
    @classmethod
    def create_text(cls, text: str, priority: int = 95):
        return cls(source="text", content=text, priority=priority)
    
    @classmethod
    def create_chat(cls, text: str, username: str, priority: int = 50):
        return cls(
            source="chat",
            content=text,
            priority=priority,
            metadata={"username": username}
        )
    
    @classmethod
    def create_proactive(cls, text: str, priority: int = 10):
        return cls(source="proactive", content=text, priority=priority)
    
    @classmethod
    def create_association(cls, text: str, trigger_data: dict, priority: int = 60):
        return cls(
            source="association",
            content=text,
            priority=priority,
            metadata={"trigger": trigger_data}
        )
    
    def __repr__(self):
        return f"Stimulus(source={self.source}, priority={self.priority}, content={self.content[:30]}...)"