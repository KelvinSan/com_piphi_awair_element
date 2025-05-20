from pydantic import BaseModel

__table__name = "AwairElement"

class DataSchema(BaseModel):
    temp: float
    humidity: float
    dew_pt: float
    aqi: float
    co2: float
    co2_est: float
    voc: float
    voc_baseline: float
    voc_h2_raw: float
    co2_est_baseline: float
    voc_ethanol_raw: float
    pm2_5: float
    pm10: float

# class AwairElement(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     time: datetime = Field(default_factory=datetime.now, nullable=False)
#     temp: float
#     humidity: float
#     dew_pt: float
#     aqi: float
#     co2: float
#     co2_est: float
#     voc: float
#     voc_baseline: float
#     voc_h2_raw: float
#     co2_est_baseline: float
#     voc_ethanol_raw: float
#     pm2_5: float
#     pm10: float
#     sensor_id: Optional[int]