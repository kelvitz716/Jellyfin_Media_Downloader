import asyncio
import logging
import aiohttp
from guessit import guessit
from tmdbv3api import TMDb, Movie, TV
from config import TMDB_API_KEY


logger = logging.getLogger(__name__)

# Initialize tmdbv3api client
tmdb = TMDb()
tmdb.api_key = TMDB_API_KEY
tmdb.language = 'en'

_movie = Movie()
_tv    = TV()

class MediaProcessor:
    """
    Parses media filenames using GuessIt and queries TMDb for movies or TV episodes.
    
    Supports two usage patterns:
    
    1. External session (injected):
        processor = MediaProcessor(filename, tmdb_api_key, session=existing_session)
        result = await processor.search_tmdb()
    
    2. Context manager (self-managed session):
        async with MediaProcessor(filename, tmdb_api_key) as processor:
            result = await processor.search_tmdb()
    """
    TMDB_URL = "https://api.themoviedb.org/3"

    def __init__(self, filename: str, tmdb_api_key: str, session: aiohttp.ClientSession = None):
        """
        Initialize MediaProcessor.
        
        Args:
            filename: Media filename to parse
            tmdb_api_key: TMDb API key
            session: Optional aiohttp session. If not provided, one will be
                     created when using the context manager.
        """
        self.filename = filename
        self.tmdb_api_key = tmdb_api_key
        self.session = session
        self._owns_session = False  # True if we created the session ourselves

    async def __aenter__(self):
        """Create session if not provided externally."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
            self._owns_session = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close session if we created it."""
        if self._owns_session and self.session:
            await self.session.close()
            self.session = None
            self._owns_session = False
        return False  # Don't suppress exceptions


    async def search_tmdb(self) -> dict:
        """
        Use tmdbv3api to lookup movie or TV episode based on GuessIt.
        """
        info = guessit(self.filename)
        title = info.get('title')
        if not title:
            raise ValueError(f"Could not extract title from '{self.filename}'")

        loop = asyncio.get_running_loop()

        # TV episode
        if info.get('type') == 'episode':
            season  = info.get('season', 1)
            episode = info.get('episode', 1)
            # run blocking .search in thread
            results = await loop.run_in_executor(None, lambda: _tv.search(title))
            if not results:
                return {}
            show = results[0]
            # fetch specific episode details (blocking)
            try:
                ep_data = await loop.run_in_executor(
                    None,
                    lambda: _tv.tv_episode(show.id, season, episode)
                )
            except Exception:
                ep_data = {}
            return {
                "type":    "tv",
                "title":   show.name,
                "season":  season,
                "episode": episode,
                "is_anime": False,  # keyword lookup not in tmdbv3api
                "tmdb_id": show.id,
            }

        # Movie
        year = info.get('year') if info.get('type') == 'movie' else None
        results = await loop.run_in_executor(None, lambda: _movie.search(title))
        if not results:
            return {}
        m = results[0]
        return {
            "type":     "movie",
            "title":    m.title,
            "year":     m.release_date[:4] if getattr(m, 'release_date', None) else None,
            "is_anime": False,
            "tmdb_id":  m.id,
        }
   
    async def check_anime_tag(self, tmdb_id: int, media_type: str) -> bool:
        """Check if 'anime' exists in TMDb keywords"""
        endpoint = f"{self.TMDB_URL}/{media_type}/{tmdb_id}/keywords"
        try:
            # fetch_json will add api_key for us
            data = await self.fetch_json(endpoint, {})
            # Handle both movie and TV keyword formats
            keywords = data.get("keywords", []) if media_type == "movie" else data.get("results", [])
            return any(k["name"].lower() == "anime" for k in keywords)
        except Exception as e:
            logger.error(f"TMDb keyword check failed: {e}")
            return False

    async def fetch_json(self, url: str, params: dict) -> dict:
        if not self.session:
             raise RuntimeError("No aiohttp session provided")
        params["api_key"] = self.tmdb_api_key
        async with self.session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()
