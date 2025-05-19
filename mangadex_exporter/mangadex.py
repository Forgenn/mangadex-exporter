"""
MangaDex API client module.
"""

from typing import Optional, Dict, Any, List, Literal, Iterator
from datetime import datetime
import httpx
import time
from pydantic import BaseModel, Field, validator

class MangaDexAuth(BaseModel):
    """MangaDex authentication model."""
    token: str
    refresh_token: str
    token_type: str
    expires_in: int

# Define the valid manga statuses
MangaStatus = Literal["reading", "on_hold", "plan_to_read", "dropped", "re_reading", "completed"]

class FeedOrder(BaseModel):
    """Order parameters for feed requests."""
    createdAt: Optional[Literal["asc", "desc"]] = None
    updatedAt: Optional[Literal["asc", "desc"]] = None
    publishAt: Optional[Literal["asc", "desc"]] = None
    readableAt: Optional[Literal["asc", "desc"]] = None
    volume: Optional[Literal["asc", "desc"]] = None
    chapter: Optional[Literal["asc", "desc"]] = None

class FeedParameters(BaseModel):
    """Parameters for manga feed requests."""
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    translatedLanguage: Optional[List[str]] = Field(None, alias="translatedLanguage[]")
    originalLanguage: Optional[List[str]] = Field(None, alias="originalLanguage[]")
    excludedOriginalLanguage: Optional[List[str]] = Field(None, alias="excludedOriginalLanguage[]")
    contentRating: List[Literal["safe", "suggestive", "erotica", "pornographic"]] = Field(
        default=["safe", "suggestive", "erotica"],
        alias="contentRating[]"
    )
    excludedGroups: Optional[List[str]] = Field(None, alias="excludedGroups[]")
    excludedUploaders: Optional[List[str]] = Field(None, alias="excludedUploaders[]")
    includeFutureUpdates: Literal["0", "1"] = "1"
    createdAtSince: Optional[str] = None
    updatedAtSince: Optional[str] = None
    publishAtSince: Optional[str] = None
    order: Optional[FeedOrder] = None
    includes: Optional[List[str]] = Field(None, alias="includes[]")
    includeEmptyPages: Optional[Literal["0", "1", "2"]] = None
    includeFuturePublishAt: Optional[Literal["0", "1", "2"]] = None
    includeExternalUrl: Optional[Literal["0", "1", "2"]] = None

    @validator("translatedLanguage", "originalLanguage", "excludedOriginalLanguage")
    def validate_language_codes(cls, v):
        if v is not None:
            for lang in v:
                if not 2 <= len(lang) <= 5 or not lang.replace("-", "").isalpha():
                    raise ValueError(f"Invalid language code: {lang}")
        return v

    @validator("excludedGroups", "excludedUploaders")
    def validate_uuids(cls, v):
        if v is not None:
            for uuid in v:
                if not len(uuid) == 36:  # Basic UUID length check
                    raise ValueError(f"Invalid UUID: {uuid}")
        return v

    @validator("createdAtSince", "updatedAtSince", "publishAtSince")
    def validate_datetime(cls, v):
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                raise ValueError(f"Invalid datetime format: {v}. Expected format: YYYY-MM-DDTHH:MM:SS")
        return v

class MangaDexClient:
    """Client for interacting with the MangaDex API."""
    
    BASE_URL = "https://api.mangadex.org"
    OAUTH_URL = "https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token"
    BATCH_SIZE = 100  # Number of manga to process in each batch
    
    def __init__(
        self,
        username: str,
        password: str,
        client_id: str,
        client_secret: str
    ):
        """Initialize the MangaDex client.
        
        Args:
            username: MangaDex username
            password: MangaDex password
            client_id: MangaDex client ID
            client_secret: MangaDex client secret
        """
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth: Optional[MangaDexAuth] = None
        self.client = httpx.Client(base_url=self.BASE_URL)
    
    def login(self) -> None:
        """Authenticate with MangaDex OAuth2 password grant."""
        response = httpx.post(
            self.OAUTH_URL,
            data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if response.status_code != 200:
            print("Login failed:", response.text)
        response.raise_for_status()
        data = response.json()
        self.auth = MangaDexAuth(
            token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data["token_type"],
            expires_in=data["expires_in"]
        )
        self.client.headers["Authorization"] = f"{self.auth.token_type} {self.auth.token}"
    
    def refresh_token(self) -> None:
        """Refresh the OAuth2 token."""
        if not self.auth:
            raise ValueError("No auth token available to refresh")
        response = httpx.post(
            self.OAUTH_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.auth.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if response.status_code != 200:
            print("Token refresh failed:", response.text)
        response.raise_for_status()
        data = response.json()
        self.auth = MangaDexAuth(
            token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data["token_type"],
            expires_in=data["expires_in"]
        )
        self.client.headers["Authorization"] = f"{self.auth.token_type} {self.auth.token}"
    
    def get_manga_feed(self, params: Optional[FeedParameters] = None) -> Dict[str, Any]:
        """
        Get the user's followed manga feed.
        
        Args:
            params: Optional feed parameters to customize the request
            
        Returns:
            Dict containing the manga feed data
        """
        if not self.auth:
            self.login()
        
        # Use default parameters if none provided
        if params is None:
            params = FeedParameters()
        
        # Prepare query parameters, flattening 'order' as needed
        query = params.model_dump(by_alias=True, exclude_none=True)
        order = query.pop('order', None)
        if order:
            for k, v in order.items():
                if v is not None:
                    query[f'order[{k}]'] = v
        
        try:
            response = self.client.get(
                "/user/follows/manga/feed",
                params=query
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token might be expired, try to refresh
                self.refresh_token()
                # Retry the request
                response = self.client.get(
                    "/user/follows/manga/feed",
                    params=query
                )
                response.raise_for_status()
                return response.json()
            raise
    
    def get_manga_details(self, manga_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a manga.
        
        Args:
            manga_id: The MangaDex manga ID
            
        Returns:
            Dict containing the manga details
        """
        if not self.auth:
            self.login()
        
        try:
            response = self.client.get(
                f"/manga/{manga_id}",
                params={"includes": ["manga"]}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token might be expired, try to refresh
                self.refresh_token()
                # Retry the request
                response = self.client.get(
                    f"/manga/{manga_id}",
                    params={"includes": ["manga"]}
                )
                response.raise_for_status()
                return response.json()
            raise
    
    def get_manga_status(self, status: Optional[MangaStatus] = None) -> Dict[str, MangaStatus]:
        """
        Get all manga reading statuses for the logged-in user.
        
        Args:
            status: Optional status filter (reading, on_hold, plan_to_read, dropped, re_reading, completed)
            
        Returns:
            Dict mapping manga IDs to their status
        """
        if not self.auth:
            self.login()
        
        try:
            params = {}
            if status:
                params["status"] = status
            
            response = self.client.get(
                "/manga/status",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            return data["statuses"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Token might be expired, try to refresh
                self.refresh_token()
                # Retry the request
                response = self.client.get(
                    "/manga/status",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                return data["statuses"]
            raise
    
    def get_manga_batch(self, manga_ids: List[str]) -> Dict[str, Any]:
        """
        Get details for a batch of manga using the /manga endpoint.
        
        Args:
            manga_ids: List of manga IDs to fetch (max 100)
            
        Returns:
            Dict containing the manga details
        """
        if not self.auth:
            self.login()
        
        if len(manga_ids) > self.BATCH_SIZE:
            raise ValueError(f"Too many manga IDs. Maximum is {self.BATCH_SIZE}")
        
        max_retries = 3
        retry_delay = 60  # 1 minute
        
        for attempt in range(max_retries):
            try:
                response = self.client.get(
                    "/manga",
                    params={
                        "ids[]": manga_ids,
                        "includes[]": ["manga"],
                        "contentRating[]": ["safe", "suggestive", "erotica"],
                        "limit": self.BATCH_SIZE
                    }
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    # Token might be expired, try to refresh
                    self.refresh_token()
                    # Retry the request
                    response = self.client.get(
                        "/manga",
                        params={
                            "ids[]": manga_ids,
                            "includes[]": ["manga"],
                            "contentRating[]": ["safe", "suggestive", "erotica"],
                            "limit": self.BATCH_SIZE
                        }
                    )
                    response.raise_for_status()
                    return response.json()
                elif e.response.status_code == 429:
                    if attempt < max_retries - 1:
                        print(f"Rate limit hit, waiting {retry_delay} seconds before retry...")
                        time.sleep(retry_delay)
                        continue
                raise
    
    def get_all_manga_details(self, manga_ids: List[str]) -> Iterator[Dict[str, Any]]:
        """
        Get details for all manga IDs in batches.
        
        Args:
            manga_ids: List of all manga IDs to fetch
            
        Yields:
            Dict containing the manga details for each batch
        """
        # Process manga IDs in batches
        for i in range(0, len(manga_ids), self.BATCH_SIZE):
            batch = manga_ids[i:i + self.BATCH_SIZE]
            yield self.get_manga_batch(batch)
    
    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close() 