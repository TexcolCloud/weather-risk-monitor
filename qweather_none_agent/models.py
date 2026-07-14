"""Shared data contracts for weather collection and report generation."""

from typing import TypedDict


class Room(TypedDict, total=False):
    name: str
    county: str
    lon: float
    lat: float


class DailyWeather(TypedDict, total=False):
    date: str
    tmax: int | None
    tmin: int | None
    textDay: str
    textNight: str
    windDay: str
    windNight: str
    precip: float
    humidity: str


class OfficialWarning(TypedDict, total=False):
    id: str
    title: str
    typeName: str
    level: str
    color: str
    levelScore: int
    text: str
    sender: str
    pubTime: str


class WeatherStats(TypedDict, total=False):
    name: str
    county: str
    tmax: int | None
    tmin: int | None
    totalPrecip: float
    rainDays: int
    maxDailyPrecip: float
    maxWind: int
    hoursAbove40: int
    maxCont40: int
    hoursAbove38: int
    maxCont38: int
    hoursAbove37: int
    maxCont37: int
    hoursAbove35: int
    maxContDaily35: int
    hoursBelow0: int
    hoursBelow5: int
    maxContBelow0: int
    maxRainHours: int
    maxPrecip: float
    maxPrecip3h: float
    maxPrecip6h: float
    maxPrecip12h: float
    maxPrecip24h: float
    dailySummary: list[DailyWeather]
    dailyDataComplete: bool
    hourlyDataComplete: bool
    hasThunder: bool
    hasSnow: bool
    hasFreezing: bool
    hasHail: bool
    hasFog: bool
    hasHaze: bool
    hasSand: bool
    officialWarnings: list[OfficialWarning]
    officialWarningLevel: str
    officialWarningTitle: str


class CountyRisk(TypedDict, total=False):
    name: str
    roomCount: int
    warnedCount: int
    maxTemp: int | None
    minTemp: int | None
    rooms: list[str]
    riskRooms: list[WeatherStats]
    officialWarnings: list[OfficialWarning]
    officialWarningLevel: str
    officialWarningTitle: str


class WeatherFetchResult(TypedDict, total=False):
    counties: list[WeatherStats]
    updateTime: str | None
    total: int
    warned: int
    failed: int
    partialFailed: int
    warningFailed: int
    dailyIncomplete: int
    failedRooms: list[str]
    partialFailedRooms: list[str]
    warningFailedRooms: list[str]
    dailyIncompleteRooms: list[str]
