"""
CLI for Google Drive operations.

Standalone command for testing and managing Google Drive integration.
"""

#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from .drive_manager import GoogleDriveManager
from ..utils.logger import Logger


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Google Drive Manager for WhatsApp Chat Auto-Export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Authenticate with Google Drive
  %(prog)s auth

  # List WhatsApp exports
  %(prog)s list

  # List exports in specific folder
  %(prog)s list --folder "My Drive"

  # Download all exports to directory
  %(prog)s download /path/to/destination

  # Download and delete from Google Drive
  %(prog)s download /path/to/destination --delete-after

  # Download from specific folder
  %(prog)s download /path/to/destination --folder "WhatsApp Backups"

  # Revoke credentials
  %(prog)s revoke
        """
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (verbose output)'
    )

    parser.add_argument(
        '--credentials-dir',
        type=str,
        metavar='DIR',
        help='Directory for OAuth credentials (default: ~/.whatsapp_export)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Auth command
    auth_parser = subparsers.add_parser('auth', help='Authenticate with Google Drive')
    auth_parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-authentication even if already authenticated'
    )

    # List command
    list_parser = subparsers.add_parser('list', help='List WhatsApp exports')
    list_parser.add_argument(
        '--folder',
        type=str,
        metavar='NAME',
        help='Folder name to search in'
    )

    # Download command
    download_parser = subparsers.add_parser('download', help='Download WhatsApp exports')
    download_parser.add_argument(
        'destination',
        help='Destination directory for downloads'
    )
    download_parser.add_argument(
        '--folder',
        type=str,
        metavar='NAME',
        help='Folder name to download from'
    )
    download_parser.add_argument(
        '--delete-after',
        action='store_true',
        help='Delete files from Google Drive after successful download'
    )

    # Revoke command
    revoke_parser = subparsers.add_parser('revoke', help='Revoke Google Drive credentials')

    return parser


def cmd_auth(manager: GoogleDriveManager, args):
    """Handle auth command."""
    logger = manager.logger

    logger.info("=" * 70)
    logger.info("Google Drive Authentication")
    logger.info("=" * 70)

    if args.force:
        logger.info("Forcing re-authentication...")
        manager.auth.revoke_credentials()

    if manager.connect():
        logger.success("Authentication successful!")
        return 0
    else:
        logger.error("Authentication failed")
        return 1


def cmd_list(manager: GoogleDriveManager, args):
    """Handle list command."""
    logger = manager.logger

    if not manager.connect():
        logger.error("Failed to connect to Google Drive")
        return 1

    # Get folder ID if specified
    folder_id = None
    if args.folder:
        folder_id, _ = manager.find_exports_in_folder(args.folder)
        if not folder_id:
            logger.error(f"Folder not found: {args.folder}")
            return 1

    # Get summary
    summary = manager.get_export_summary(folder_id=folder_id)

    logger.info("=" * 70)
    logger.info("WhatsApp Export Summary")
    logger.info("=" * 70)
    logger.info(f"Total files: {summary['file_count']}")
    logger.info(f"Total size: {summary['total_size_mb']:.2f} MB")
    logger.info("=" * 70)

    if summary['files']:
        logger.info("\nFiles:")
        for i, file in enumerate(summary['files'], 1):
            size_mb = int(file.get('size', 0)) / (1024 * 1024)
            logger.info(f"{i:3d}. {file['name']} ({size_mb:.2f} MB)")

    return 0


def cmd_download(manager: GoogleDriveManager, args):
    """Handle download command."""
    logger = manager.logger

    if not manager.connect():
        logger.error("Failed to connect to Google Drive")
        return 1

    # Validate destination
    dest_dir = Path(args.destination).expanduser()
    logger.info(f"Destination: {dest_dir}")

    # Get folder ID if specified
    folder_id = None
    if args.folder:
        folder_id, files = manager.find_exports_in_folder(args.folder)
        if not folder_id:
            logger.error(f"Folder not found: {args.folder}")
            return 1
    else:
        files = manager.list_whatsapp_exports()

    if not files:
        logger.warning("No WhatsApp exports found")
        return 0

    # Download files
    logger.info("=" * 70)
    logger.info("Downloading WhatsApp Exports")
    logger.info("=" * 70)

    downloaded = manager.batch_download_exports(
        files,
        dest_dir,
        delete_after=args.delete_after
    )

    logger.info("=" * 70)
    logger.success(f"Downloaded {len(downloaded)} file(s) to: {dest_dir}")
    logger.info("=" * 70)

    return 0


def cmd_revoke(manager: GoogleDriveManager, args):
    """Handle revoke command."""
    logger = manager.logger

    logger.info("=" * 70)
    logger.info("Revoking Google Drive Credentials")
    logger.info("=" * 70)

    if manager.auth.revoke_credentials():
        logger.success("Credentials revoked successfully")
        return 0
    else:
        logger.error("Failed to revoke credentials")
        return 1


def main():
    """Main entry point for Google Drive CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Create logger
    logger = Logger(debug=args.debug)

    # Create manager
    credentials_dir = Path(args.credentials_dir) if args.credentials_dir else None
    manager = GoogleDriveManager(credentials_dir=credentials_dir, logger=logger)

    # Execute command
    try:
        if args.command == 'auth':
            return cmd_auth(manager, args)
        elif args.command == 'list':
            return cmd_list(manager, args)
        elif args.command == 'download':
            return cmd_download(manager, args)
        elif args.command == 'revoke':
            return cmd_revoke(manager, args)
        else:
            logger.error(f"Unknown command: {args.command}")
            return 1

    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
