"""
Main application module for the MangaDex Exporter.
"""

import os
import json
import time
import logging
import argparse
from typing import Dict, Any, Optional, List, Set
from dotenv import load_dotenv
from rich.console import Console, Group
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich import print as rprint
from rich.table import Table
from .mangadex import MangaDexClient, MangaStatus
from .anilist import AniListClient

# Configure logging
console = Console()
log = logging.getLogger("mangadex_exporter")

def get_manga_title(manga_data: Dict[str, Any]) -> Optional[str]:
    """Extract the manga title from MangaDex data.
    
    Args:
        manga_data: Dictionary containing manga data from MangaDex API
        
    Returns:
        The manga title in English if available, otherwise the first available title
    """
    try:
        manga = manga_data["data"]
        attributes = manga.get("attributes", {})
        titles = attributes.get("title", {})
        
        # Try to get English title first
        if "en" in titles:
            return titles["en"]
        
        # If no English title, get the first available title
        for lang, title in titles.items():
            if title:
                return title
        
        return None
    except (KeyError, AttributeError):
        return None

def load_progress() -> Dict[str, Any]:
    """Load progress from the progress file."""
    try:
        with open("data/sync_progress.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            # Convert processed_manga list to set
            data["processed_manga"] = set(data["processed_manga"])
            return data
    except FileNotFoundError:
        return {
            "processed_manga": set(),
            "non_matched": {}
        }

def save_progress(processed_manga: Set[str], non_matched: Dict[str, Dict[str, Any]]) -> None:
    """Save progress to the progress file."""
    with open("data/sync_progress.json", "w", encoding="utf-8") as f:
        json.dump({
            "processed_manga": list(processed_manga),  # Convert set to list for JSON serialization
            "non_matched": non_matched
        }, f, indent=2, ensure_ascii=False)

def load_manga_statuses() -> Optional[Dict[str, Any]]:
    """Load manga statuses from file if it exists."""
    try:
        with open("data/manga_statuses.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def save_manga_statuses(manga_statuses: Dict[str, Any]) -> None:
    """Save manga statuses to file."""
    with open("data/manga_statuses.json", "w", encoding="utf-8") as f:
        json.dump(manga_statuses, f, indent=2, ensure_ascii=False)

def main():
    """Main application entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="MangaDex Exporter")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh manga statuses from MangaDex")
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Get configuration from environment
    debug = os.getenv("DEBUG", "false").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # Set up logging
    logging.basicConfig(
        level=log_level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)]
    )
    
    # Get MangaDex credentials
    username = os.getenv("MANGADEX_USERNAME")
    password = os.getenv("MANGADEX_PASSWORD")
    client_id = os.getenv("MANGADEX_CLIENT_ID")
    client_secret = os.getenv("MANGADEX_CLIENT_SECRET")
    
    if not all([username, password, client_id, client_secret]):
        raise ValueError(
            "MANGADEX_USERNAME, MANGADEX_PASSWORD, MANGADEX_CLIENT_ID, and "
            "MANGADEX_CLIENT_SECRET must be set in .env file"
        )
    
    # Get AniList credentials
    anilist_client_id = os.getenv("ANILIST_CLIENT_ID")
    anilist_redirect_uri = os.getenv("ANILIST_REDIRECT_URI", "http://localhost:8080")
    
    if not anilist_client_id:
        raise ValueError("ANILIST_CLIENT_ID must be set in .env file")
    
    # Display configuration
    console.print(Panel.fit(
        f"[bold blue]MangaDex Exporter[/bold blue]\n"
        f"Mode: [yellow]{'debug' if debug else 'production'}[/yellow]\n"
        f"Log level: [yellow]{log_level}[/yellow]\n"
        f"Force refresh: [yellow]{'Yes' if args.force_refresh else 'No'}[/yellow]",
        title="Configuration"
    ))
    
    # Initialize MangaDex client
    md_client = MangaDexClient(
        username=username,
        password=password,
        client_id=client_id,
        client_secret=client_secret
    )
    
    # Initialize AniList client
    al_client = AniListClient(
        client_id=anilist_client_id,
        redirect_uri=anilist_redirect_uri
    )
    
    try:
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        
        # Create progress display
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        )
        
        # Get manga statuses
        manga_statuses = None
        if not args.force_refresh:
            manga_statuses = load_manga_statuses()
            if manga_statuses:
                console.print(Panel.fit(
                    f"[green]✓[/green] Loaded manga statuses from file\n"
                    f"[green]✓[/green] Found {len(manga_statuses)} manga in your follows",
                    title="MangaDex Status"
                ))
        
        if args.force_refresh or not manga_statuses:
            with Live(progress, refresh_per_second=10) as live:
                task = progress.add_task("[bold green]Fetching manga statuses from MangaDex...", total=None)
                manga_statuses = md_client.get_manga_status()
                progress.update(task, completed=True, total=1)
            
            # Save statuses to file
            save_manga_statuses(manga_statuses)
            
            console.print(Panel.fit(
                f"[green]✓[/green] Successfully exported manga statuses to data/manga_statuses.json\n"
                f"[green]✓[/green] Found {len(manga_statuses)} manga in your follows",
                title="MangaDex Status"
            ))
        
        # Load progress
        progress_data = load_progress()
        processed_manga = progress_data["processed_manga"]  # Already a set from load_progress
        non_matched = progress_data.get("non_matched", {})
        
        if processed_manga:
            console.print(Panel.fit(
                f"[yellow]ℹ[/yellow] Resuming from previous run\n"
                f"Already processed: [yellow]{len(processed_manga)}[/yellow] manga\n"
                f"Non-matched manga: [yellow]{len(non_matched)}[/yellow]",
                title="Progress Status"
            ))
        
        # Authenticate with AniList
        console.print(Panel.fit(
            "[bold blue]Authenticating with AniList...[/bold blue]\n"
            "[yellow]ℹ[/yellow] A browser window will open for you to authorize the application\n"
            "[yellow]ℹ[/yellow] After authorizing, you can close the browser window",
            title="AniList Authentication"
        ))
        al_client.login()
        console.print(Panel.fit(
            "[green]✓[/green] Successfully authenticated with AniList!",
            title="Authentication Status"
        ))
        
        # Process manga follows
        console.print(Panel.fit(
            "[bold blue]Processing manga follows...[/bold blue]",
            title="Processing Status"
        ))
        
        # Get all manga IDs
        manga_ids = [md_id for md_id in manga_statuses.keys() if md_id not in processed_manga]
        
        # Process manga in batches
        total_batches = (len(manga_ids) + md_client.BATCH_SIZE - 1) // md_client.BATCH_SIZE
        
        # Create a panel for current manga status
        current_manga_panel = Panel(
            "[yellow]Waiting to start...[/yellow]",
            title="Current Manga",
            border_style="blue"
        )
        
        with Live(
            Group(
                progress,
                current_manga_panel
            ),
            refresh_per_second=10,
            vertical_overflow="visible"
        ) as live:
            batch_task = progress.add_task("[cyan]Processing batches...", total=total_batches)
            
            for i in range(0, len(manga_ids), md_client.BATCH_SIZE):
                batch_ids = manga_ids[i:i + md_client.BATCH_SIZE]
                current_batch = i // md_client.BATCH_SIZE + 1
                
                try:
                    # Get manga details for the batch
                    batch_task = progress.add_task(
                        f"[bold green]Fetching batch {current_batch} of {total_batches}...",
                        total=None
                    )
                    batch_data = md_client.get_manga_batch(batch_ids)
                    progress.update(batch_task, completed=True, total=1)
                    progress.remove_task(batch_task)
                    
                    # Process each manga in the batch
                    manga_task = progress.add_task(
                        f"[yellow]Processing manga in batch {current_batch}...",
                        total=len(batch_data.get("data", []))
                    )
                    
                    for manga in batch_data.get("data", []):
                        md_id = manga["id"]
                        status = manga_statuses[md_id]
                        
                        try:
                            title = get_manga_title({"data": manga})
                            
                            if not title:
                                live.update(
                                    Group(
                                        progress,
                                        Panel(
                                            f"[red]Could not find title for manga {md_id}[/red]",
                                            title="Current Manga",
                                            border_style="red"
                                        )
                                    )
                                )
                                processed_manga.add(md_id)
                                progress.advance(manga_task)
                                continue
                            
                            # Update panel with current manga
                            live.update(
                                Group(
                                    progress,
                                    Panel(
                                        f"Title: [yellow]{title}[/yellow]\n"
                                        f"Status: [yellow]{status}[/yellow]\n"
                                        f"Action: [blue]Searching on AniList...[/blue]",
                                        title="Current Manga",
                                        border_style="blue"
                                    )
                                )
                            )
                            
                            # Search for the manga on AniList
                            search_results = al_client.search_manga(title)
                            
                            # Process search results
                            if "data" in search_results and "Page" in search_results["data"]:
                                media = search_results["data"]["Page"]["media"]
                                if media:
                                    # Use the first result
                                    manga = media[0]
                                    anilist_title = manga['title']['romaji']
                                    
                                    # Map MangaDex status to AniList status
                                    anilist_status = {
                                        "reading": "CURRENT",
                                        "on_hold": "PAUSED",
                                        "plan_to_read": "PLANNING",
                                        "dropped": "DROPPED",
                                        "re_reading": "REPEATING",
                                        "completed": "COMPLETED"
                                    }.get(status, "CURRENT")
                                    
                                    # Update panel with found manga
                                    live.update(
                                        Group(
                                            progress,
                                            Panel(
                                                f"Title: [green]{anilist_title}[/green]\n"
                                                f"Status: [yellow]{status}[/yellow]\n"
                                                f"Action: [blue]Adding to AniList...[/blue]",
                                                title="Current Manga",
                                                border_style="blue"
                                            )
                                        )
                                    )
                                    
                                    # Add to AniList
                                    result = al_client.save_manga_follow(manga["id"], status=anilist_status)
                                    final_status = result['data']['SaveMediaListEntry']['status']
                                    
                                    # Update panel with success
                                    live.update(
                                        Group(
                                            progress,
                                            Panel(
                                                f"Title: [green]{anilist_title}[/green]\n"
                                                f"Status: [green]{final_status}[/green]\n"
                                                f"Action: [green]Successfully added to AniList[/green]",
                                                title="Current Manga",
                                                border_style="green"
                                            )
                                        )
                                    )
                                else:
                                    # Add to non-matched list
                                    non_matched[md_id] = {
                                        "title": title,
                                        "status": status
                                    }
                                    # Update panel with not found
                                    live.update(
                                        Group(
                                            progress,
                                            Panel(
                                                f"Title: [yellow]{title}[/yellow]\n"
                                                f"Status: [yellow]{status}[/yellow]\n"
                                                f"Action: [red]Not found on AniList[/red]",
                                                title="Current Manga",
                                                border_style="yellow"
                                            )
                                        )
                                    )
                            else:
                                # Add to non-matched list
                                non_matched[md_id] = {
                                    "title": title,
                                    "status": status
                                }
                                # Update panel with error
                                live.update(
                                    Group(
                                        progress,
                                        Panel(
                                            f"Title: [red]{title}[/red]\n"
                                            f"Status: [yellow]{status}[/yellow]\n"
                                            f"Action: [red]Error searching on AniList[/red]",
                                            title="Current Manga",
                                            border_style="red"
                                        )
                                    )
                                )
                            
                            # Mark as processed
                            processed_manga.add(md_id)
                            
                            # Save progress after each manga
                            save_progress(processed_manga, non_matched)
                            
                            # Rate limiting: wait 1 second between AniList requests
                            time.sleep(1)
                            
                        except Exception as e:
                            log.error(f"Error processing manga {md_id}: {str(e)}")
                            continue
                        
                        progress.advance(manga_task)
                    
                    progress.remove_task(manga_task)
                    progress.advance(batch_task)
                    
                    # Rate limiting: wait 1 second between MangaDex batches
                    time.sleep(1)
                    
                except Exception as e:
                    log.error(f"Error processing batch: {str(e)}")
                    # Save progress before exiting
                    save_progress(processed_manga, non_matched)
                    raise
        
        # Save final non-matched manga list
        non_matched_file = "data/non_matched_manga.json"
        with open(non_matched_file, "w", encoding="utf-8") as f:
            json.dump({
                "total": len(non_matched),
                "manga": non_matched
            }, f, indent=2, ensure_ascii=False)
        
        console.print(Panel.fit(
            f"[bold green]Manga sync completed![/bold green]\n"
            f"Total manga processed: [yellow]{len(processed_manga)}[/yellow]\n"
            f"Non-matched manga: [yellow]{len(non_matched)}[/yellow]\n"
            f"See [blue]{non_matched_file}[/blue] for details of non-matched manga.",
            title="Results"
        ))
        
    finally:
        md_client.close()
        al_client.close()

if __name__ == "__main__":
    main() 