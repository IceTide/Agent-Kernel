#!/usr/bin/env python3
"""
Vector Database Management Script for Hospital Simulation.

This script provides utilities to manage Milvus vector database collections:
- List all collections
- Show collection details
- Drop/delete collections
- Get collection statistics

Run the script and follow the interactive menu.
Press Ctrl+C to exit.
"""

import asyncio
import sys
from typing import List, Optional

try:
    from pymilvus import MilvusException
except ImportError:
    MilvusException = Exception
MILVUS_URI = "http://localhost:19530"


class Color:
    """Terminal color codes."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Color.BOLD}{Color.CYAN}{'=' * 60}{Color.END}")
    print(f"{Color.BOLD}{Color.CYAN}{text}{Color.END}")
    print(f"{Color.BOLD}{Color.CYAN}{'=' * 60}{Color.END}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Color.GREEN}✅ {text}{Color.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Color.RED}❌ {text}{Color.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Color.YELLOW}⚠️  {text}{Color.END}")


def print_info(text: str):
    """Print info message."""
    print(f"{Color.BLUE}ℹ️  {text}{Color.END}")


def print_menu():
    """Print the main menu."""
    print_header("Vector Database Management")
    print(f"{Color.BOLD}Please select an option:{Color.END}\n")
    print(f"  {Color.CYAN}1.{Color.END} List all collections")
    print(f"  {Color.CYAN}2.{Color.END} Show collection details")
    print(f"  {Color.CYAN}3.{Color.END} Show collection statistics")
    print(f"  {Color.CYAN}4.{Color.END} Drop collection(s)")
    print(f"  {Color.CYAN}0.{Color.END} Exit")
    print()


class VectorDBManager:
    """Manager for Milvus vector database operations."""

    def __init__(self, milvus_uri: str):
        """
        Initialize the VectorDBManager.

        Args:
            milvus_uri: Milvus server URI
        """
        self.milvus_uri = milvus_uri
        self.connections = None

    async def connect(self) -> bool:
        """Connect to Milvus server."""
        try:
            from pymilvus import connections

            self.connections = connections
            if not self.connections.has_connection("default"):
                self.connections.connect(
                    alias="default",
                    uri=self.milvus_uri
                )
            print_success(f"Connected to Milvus at {self.milvus_uri}")
            return True
        except Exception as e:
            print_error(f"Failed to connect to Milvus: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Milvus server."""
        try:
            if self.connections and self.connections.has_connection("default"):
                self.connections.disconnect("default")
                print_success("Disconnected from Milvus")
        except Exception as e:
            print_warning(f"Warning during disconnect: {e}")

    async def list_collections(self) -> List[str]:
        """
        List all collections in the database.

        Returns:
            List of collection names
        """
        try:
            from pymilvus import utility

            collections = utility.list_collections()
            return collections
        except Exception as e:
            print_error(f"Failed to list collections: {e}")
            return []

    async def get_collection_info(self, collection_name: str) -> Optional[dict]:
        """
        Get detailed information about a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary with collection information
        """
        try:
            from pymilvus import Collection

            if collection_name not in await self.list_collections():
                print_error(f"Collection '{collection_name}' does not exist")
                return None

            collection = Collection(collection_name)
            collection.load()

            info = {
                "name": collection_name,
                "num_entities": collection.num_entities,
                "description": collection.description,
            }
            try:
                indexes = collection.indexes
                if indexes:
                    info["indexes"] = []
                    for index in indexes:
                        index_info = {
                            "name": getattr(index, 'index_name', getattr(index, 'name', 'unknown')),
                            "field_name": getattr(index, 'field_name', getattr(index, 'field', 'unknown')),
                        }
                        try:
                            index_info["index_type"] = index.index_type
                        except AttributeError:
                            try:
                                if hasattr(index, 'params') and 'index_type' in index.params:
                                    index_info["index_type"] = index.params['index_type']
                                else:
                                    index_info["index_type"] = "unknown"
                            except:
                                index_info["index_type"] = "unknown"

                        info["indexes"].append(index_info)
            except Exception as idx_error:
                print_warning(f"Could not retrieve index information: {idx_error}")

            return info

        except Exception as e:
            print_error(f"Failed to get collection info: {e}")
            return None

    async def drop_collection(self, collection_name: str) -> bool:
        """
        Drop/delete a collection.

        Args:
            collection_name: Name of the collection to drop

        Returns:
            True if successful, False otherwise
        """
        try:
            from pymilvus import utility

            if collection_name not in await self.list_collections():
                print_error(f"Collection '{collection_name}' does not exist")
                return False
            info = await self.get_collection_info(collection_name)
            entity_count = info.get("num_entities", 0) if info else 0
            utility.drop_collection(collection_name)

            print_success(f"Successfully dropped collection '{collection_name}'")
            print_info(f"Entities deleted: {entity_count}")

            return True

        except Exception as e:
            print_error(f"Failed to drop collection: {e}")
            return False

    async def get_collection_stats(self, collection_name: str) -> Optional[dict]:
        """
        Get statistics for a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary with statistics
        """
        try:
            from pymilvus import Collection

            if collection_name not in await self.list_collections():
                print_error(f"Collection '{collection_name}' does not exist")
                return None

            collection = Collection(collection_name)
            collection.load()

            stats = {
                "name": collection_name,
                "num_entities": collection.num_entities,
                "schema": {
                    "fields": []
                }
            }
            for field in collection.schema.fields:
                stats["schema"]["fields"].append({
                    "name": field.name,
                    "type": str(field.dtype),
                    "is_primary": field.is_primary,
                })

            return stats

        except Exception as e:
            print_error(f"Failed to get collection stats: {e}")
            return None


async def handle_list_collections(manager: VectorDBManager):
    """Handle listing all collections."""
    print_header("Collections in Database")

    collections = await manager.list_collections()
    if not collections:
        print_warning("No collections found.")
    else:
        for i, coll_name in enumerate(collections, 1):
            print(f"  {Color.GREEN}{i}.{Color.END} {Color.BOLD}{coll_name}{Color.END}")

        print(f"\n{Color.CYAN}Total: {len(collections)} collection(s){Color.END}")


async def handle_show_info(manager: VectorDBManager):
    """Handle showing collection details."""
    print_header("Collection Details")

    collection_name = input(f"{Color.CYAN}Enter collection name: {Color.END}").strip()

    if not collection_name:
        print_warning("No collection name provided")
        return

    info = await manager.get_collection_info(collection_name)
    if info:
        print(f"\n{Color.BOLD}Name:{Color.END} {info['name']}")
        print(f"{Color.BOLD}Entities:{Color.END} {info['num_entities']}")
        if info.get('description'):
            print(f"{Color.BOLD}Description:{Color.END} {info['description']}")
        if info.get('indexes'):
            print(f"{Color.BOLD}Indexes:{Color.END}")
            for idx in info['indexes']:
                print(f"  - {idx['name']} ({idx['index_type']}) on field '{idx['field_name']}'")


async def handle_show_stats(manager: VectorDBManager):
    """Handle showing collection statistics."""
    print_header("Collection Statistics")

    collection_name = input(f"{Color.CYAN}Enter collection name: {Color.END}").strip()

    if not collection_name:
        print_warning("No collection name provided")
        return

    stats = await manager.get_collection_stats(collection_name)
    if stats:
        print(f"\n{Color.BOLD}Name:{Color.END} {stats['name']}")
        print(f"{Color.BOLD}Number of entities:{Color.END} {stats['num_entities']}")
        print(f"{Color.BOLD}Schema:{Color.END}")
        for field in stats['schema']['fields']:
            primary_marker = f"{Color.GREEN}[PRIMARY]{Color.END} " if field['is_primary'] else ""
            print(f"  - {field['name']}: {field['type']} {primary_marker}")


async def handle_drop_collections(manager: VectorDBManager):
    """Handle dropping collections."""
    print_header("Drop Collections")
    print_warning("This is a destructive operation that cannot be undone!")

    input_str = input(f"{Color.CYAN}Enter collection name(s) to drop (comma-separated): {Color.END}").strip()

    if not input_str:
        print_warning("No collection names provided")
        return

    collection_names = [name.strip() for name in input_str.split(',')]
    print(f"\n{Color.RED}You are about to drop the following collections:{Color.END}")
    for name in collection_names:
        print(f"  - {Color.BOLD}{name}{Color.END}")

    confirm = input(f"\n{Color.YELLOW}Type 'yes' to confirm: {Color.END}").strip().lower()

    if confirm not in ['yes', 'y']:
        print_warning("Operation cancelled")
        return
    for coll_name in collection_names:
        print(f"\n{Color.CYAN}Dropping collection: {coll_name}{Color.END}")
        success = await manager.drop_collection(coll_name)
        if success:
            print_success(f"Collection '{coll_name}' dropped successfully")
        else:
            print_error(f"Failed to drop collection '{coll_name}'")


async def interactive_loop(manager: VectorDBManager):
    """Main interactive loop."""
    while True:
        try:
            print_menu()

            choice = input(f"{Color.CYAN}Enter your choice [0-4]: {Color.END}").strip()

            if choice == '0':
                print_info("Exiting...")
                break
            elif choice == '1':
                await handle_list_collections(manager)
            elif choice == '2':
                await handle_show_info(manager)
            elif choice == '3':
                await handle_show_stats(manager)
            elif choice == '4':
                await handle_drop_collections(manager)
            else:
                print_warning(f"Invalid choice: {choice}")
            input(f"\n{Color.YELLOW}Press Enter to continue...{Color.END}")

        except KeyboardInterrupt:
            print(f"\n\n{Color.YELLOW}Interrupted by user. Exiting...{Color.END}")
            break
        except Exception as e:
            print_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main function."""
    print_header("Vector Database Management Tool")
    print_info(f"Connecting to Milvus at {MILVUS_URI}...")
    manager = VectorDBManager(MILVUS_URI)

    if not await manager.connect():
        print_error("Failed to connect to Milvus. Exiting.")
        return

    try:
        await interactive_loop(manager)

    finally:
        await manager.disconnect()

    print_success("Done!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}Program interrupted by user.{Color.END}")
        sys.exit(0)
