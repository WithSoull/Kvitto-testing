from pydantic import BaseModel, ConfigDict, Field


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(examples=["standard"])
    title: str = Field(examples=["Standard"])
    price: int = Field(description="Price in kopecks", examples=[1990000])
