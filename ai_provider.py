from abc import ABC, abstractmethod

class AIProvider(ABC):
    @abstractmethod
    async def generate_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        pass