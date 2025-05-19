"""
AniList API client module.
"""

from typing import Optional, Dict, Any
import webbrowser
import http.server
import urllib.parse
import threading
import json
import time
import httpx
from pydantic import BaseModel

class AniListAuth(BaseModel):
    """AniList authentication model."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None

class AniListClient:
    """AniList API client."""
    
    AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
    API_URL = "https://graphql.anilist.co"
    DEFAULT_REDIRECT_URI = "http://localhost:8080"
    RATE_LIMIT_THRESHOLD = 61  # Keep 61 requests in reserve (90 - 29 for degraded API)
    RATE_LIMIT_WINDOW = 60  # Rate limit window in seconds
    
    def __init__(self, client_id: str, redirect_uri: str = DEFAULT_REDIRECT_URI):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.auth: Optional[AniListAuth] = None
        self.client = httpx.Client(base_url=self.API_URL)
        self._auth_event = threading.Event()
        self._rate_limit_remaining = 90  # Default rate limit
        self._last_request_time = 0
    
    def _check_rate_limit(self) -> None:
        """
        Check if we're approaching the rate limit and wait if necessary.
        """
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        
        # If we're approaching the rate limit threshold, wait
        if self._rate_limit_remaining <= self.RATE_LIMIT_THRESHOLD:
            wait_time = self.RATE_LIMIT_WINDOW - time_since_last_request
            if wait_time > 0:
                print(f"Approaching rate limit ({self._rate_limit_remaining} remaining), waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                self._rate_limit_remaining = 90  # Reset after waiting
                self._last_request_time = time.time()
    
    def _update_rate_limit(self, response: httpx.Response) -> None:
        """
        Update rate limit information from response headers.
        """
        if "X-RateLimit-Remaining" in response.headers:
            self._rate_limit_remaining = int(response.headers["X-RateLimit-Remaining"])
        self._last_request_time = time.time()
    
    def _start_auth_server(self) -> None:
        """Start a local server to receive the access token from URL fragment."""
        class AuthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                # Check for error response
                if "error=" in self.path:
                    error_params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                    error = error_params.get("error", [""])[0]
                    error_description = error_params.get("error_description", [""])[0]
                    self.send_response(400)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"Authorization failed: {error} - {error_description}".encode())
                    return
                # Serve the HTML page that will handle the fragment
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    html = """
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>AniList Authorization</title>
                    </head>
                    <body>
                        <h1>Processing authorization...</h1>
                        <script>
                            // Extract fragment parameters
                            const fragment = window.location.hash.substring(1);
                            const params = new URLSearchParams(fragment);
                            // Send parameters to server
                            fetch('/callback?' + params.toString())
                                .then(response => response.text())
                                .then(text => {
                                    document.body.innerHTML = text;
                                })
                                .catch(error => {
                                    document.body.innerHTML = 'Error: ' + error;
                                });
                        </script>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode())
                    return
                # Handle the callback with the fragment parameters
                if self.path.startswith("/callback"):
                    params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                    if "access_token" in params:
                        self.server.client.auth = AniListAuth(
                            access_token=params["access_token"][0],
                            token_type=params.get("token_type", ["Bearer"])[0],
                            expires_in=int(params.get("expires_in", ["0"])[0])
                        )
                        self.server.client._auth_event.set()
                        # Send success response
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(b"Authorization successful! You can close this window.")
                        return
                    else:
                        # Not the final redirect, just show a waiting page or ignore
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(b"Waiting for authorization... (no access token yet)")
                        return
                # Send error response for any other path
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"Authorization failed! Please try again.")
        
        print(f"Starting local server on {self.redirect_uri}")
        # Create server with access to the client instance
        server = http.server.HTTPServer(("localhost", 8080), AuthHandler)
        server.client = self
        
        # Start server in a separate thread
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # Wait for access token
        print("Waiting for authorization...")
        self._auth_event.wait()
        print("Authorization completed!")
        
        # Shutdown server
        server.shutdown()
        server.server_close()
    
    def login(self) -> None:
        """Authenticate with AniList using OAuth2 implicit grant flow."""
        # Open browser for user authorization
        auth_url = (
            f"{self.AUTH_URL}?"
            f"client_id={self.client_id}&"
            f"response_type=token"
        )
        print(f"Opening browser with auth URL: {auth_url}")
        webbrowser.open(auth_url)
        
        # Start local server to receive the access token
        self._start_auth_server()
        
        if not self.auth:
            raise ValueError("Failed to receive access token")
        
        # Set the authorization header for future requests
        self.client.headers["Authorization"] = f"{self.auth.token_type} {self.auth.access_token}"
        print("Successfully set up AniList authentication!")
    
    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
    
    def save_manga_follow(self, media_id: int, status: str = "CURRENT") -> Dict[str, Any]:
        """
        Save a manga to the user's AniList list.
        
        Args:
            media_id: The AniList media ID
            status: The status to set (CURRENT, PLANNING, COMPLETED, DROPPED, PAUSED, REPEATING)
            
        Returns:
            Dict containing the response from AniList
        """
        if not self.auth:
            raise ValueError("Not authenticated with AniList")
        
        max_retries = 3
        retry_delay = 60  # 1 minute
        
        query = """
        mutation ($mediaId: Int, $status: MediaListStatus) {
            SaveMediaListEntry(mediaId: $mediaId, status: $status) {
                id
                status
            }
        }
        """
        
        variables = {
            "mediaId": media_id,
            "status": status
        }
        
        for attempt in range(max_retries):
            try:
                self._check_rate_limit()
                response = self.client.post(
                    "",
                    json={
                        "query": query,
                        "variables": variables
                    }
                )
                self._update_rate_limit(response)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    if attempt < max_retries - 1:
                        print(f"AniList rate limit hit, waiting {retry_delay} seconds before retry...")
                        time.sleep(retry_delay)
                        continue
                raise
    
    def search_manga(self, title: str) -> Dict[str, Any]:
        """
        Search for a manga on AniList by title.
        
        Args:
            title: The manga title to search for
            
        Returns:
            Dict containing the search results
        """
        if not self.auth:
            raise ValueError("Not authenticated with AniList")
        
        max_retries = 3
        retry_delay = 60  # 1 minute
        
        query = """
        query ($search: String) {
            Page {
                media(search: $search, type: MANGA) {
                    id
                    title {
                        romaji
                        english
                    }
                }
            }
        }
        """
        
        variables = {
            "search": title
        }
        
        for attempt in range(max_retries):
            try:
                self._check_rate_limit()
                response = self.client.post(
                    "",
                    json={
                        "query": query,
                        "variables": variables
                    }
                )
                self._update_rate_limit(response)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    if attempt < max_retries - 1:
                        print(f"AniList rate limit hit, waiting {retry_delay} seconds before retry...")
                        time.sleep(retry_delay)
                        continue
                raise 