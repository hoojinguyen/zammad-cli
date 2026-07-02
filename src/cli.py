import os
import sys
import argparse
from src.utils import setup_logging, log_error, get_install_dir, Colors
from src.installer import run_installation, uninstall_zammad
from src.manager import start_services, stop_services, restart_services, show_status, stream_logs, get_web_port, health_check
from src.db import open_db_shell, show_db_info, backup_db, restore_db
from src.backup import backup_volumes, restore_volumes, list_backups

def run_interactive_menu():
    """Starts the interactive terminal user interface."""
    setup_logging()
    
    while True:
        os.system('clear' if os.name != 'nt' else 'cls')
        
        install_dir = get_install_dir()
        config_exists = os.path.exists(os.path.join(install_dir, ".env"))
        
        print(f"{Colors.BOLD}{Colors.CYAN}===================================================={Colors.NC}")
        print(f"{Colors.BOLD}{Colors.CYAN}            Zammad Helpdesk Control Center          {Colors.NC}")
        print(f"{Colors.BOLD}{Colors.CYAN}===================================================={Colors.NC}")
        
        if config_exists:
            try:
                import subprocess
                res = subprocess.run(["docker", "compose", "ps", "--format", "json"], cwd=install_dir, capture_output=True, text=True)
                if "running" in res.stdout:
                    status_str = f"{Colors.GREEN}RUNNING (Active){Colors.NC}"
                else:
                    status_str = f"{Colors.YELLOW}STOPPED (Inactive){Colors.NC}"
            except Exception:
                status_str = f"{Colors.RED}UNKNOWN (Docker error){Colors.NC}"
                
            web_port = get_web_port()
            web_port_str = f" | Web Port: {Colors.CYAN}{web_port}{Colors.NC}"
        else:
            status_str = f"{Colors.RED}NOT INSTALLED{Colors.NC}"
            web_port_str = ""
            
        print(f"  Current Status: {status_str}{web_port_str}")
        print(f"  Install Directory: {Colors.BLUE}{install_dir}{Colors.NC}")
        print(f"{Colors.BOLD}{Colors.CYAN}===================================================={Colors.NC}")
        print("  1)  Install / Reinstall Zammad")
        print("  2)  Start Zammad Services")
        print("  3)  Stop Zammad Services")
        print("  4)  Restart Zammad Services")
        print("  5)  View Container Status")
        print("  6)  Stream Live Logs")
        print("  7)  Open Database Terminal Shell (PostgreSQL)")
        print("  8)  View Database Connection Guide")
        print("  9)  Backup Database (SQL Dump)")
        print("  10) Restore Database (SQL Dump)")
        print("  11) Backup Zammad Volumes (Full Stack Backup)")
        print("  12) List Volume Backups")
        print("  13) Restore Zammad Volumes (Full Stack Restore)")
        print("  14) Run Health Checks")
        print("  15) Uninstall Zammad Stack")
        print("  16) Exit Control Center")
        print(f"{Colors.BOLD}{Colors.CYAN}===================================================={Colors.NC}")
        
        try:
            choice = input(f"{Colors.BOLD}Enter choice [1-16]: {Colors.NC}").strip()
            
            if choice == "1":
                run_installation()
            elif choice == "2":
                start_services()
            elif choice == "3":
                stop_services()
            elif choice == "4":
                restart_services()
            elif choice == "5":
                show_status()
            elif choice == "6":
                stream_logs(follow=True)
            elif choice == "7":
                open_db_shell()
            elif choice == "8":
                show_db_info()
            elif choice == "9":
                backup_db()
            elif choice == "10":
                backup_path = input("Enter path to SQL backup file: ").strip()
                if backup_path:
                    restore_db(backup_path)
                else:
                    print("No backup file provided.")
            elif choice == "11":
                backup_volumes()
            elif choice == "12":
                list_backups()
            elif choice == "13":
                backup_name = input("Enter volume backup filename (e.g. zammad-backup-xxx.tar.gz): ").strip()
                if backup_name:
                    restore_volumes(backup_name)
                else:
                    print("No backup file provided.")
            elif choice == "14":
                health_check()
            elif choice == "15":
                uninstall_zammad()
            elif choice == "16" or choice.lower() in ["exit", "q", "quit"]:
                print(f"\n{Colors.GREEN}Goodbye!{Colors.NC}\n")
                break
            else:
                print(f"\n{Colors.RED}Invalid option, please choose between 1 and 16.{Colors.NC}")
                
            input(f"\n{Colors.YELLOW}Press Enter to return to menu...{Colors.NC}")
            
        except KeyboardInterrupt:
            print(f"\n\n{Colors.GREEN}Goodbye!{Colors.NC}\n")
            break
        except Exception as e:
            log_error(f"Error executing command: {e}")
            input(f"\n{Colors.YELLOW}Press Enter to return to menu...{Colors.NC}")

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Zammad Helpdesk CLI Controller Wrapper.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Management Subcommands")
    
    # install
    subparsers.add_parser("install", help="Install Zammad stack and setup environment.")
    
    # start
    subparsers.add_parser("start", help="Start the Zammad containers.")
    
    # stop
    subparsers.add_parser("stop", help="Stop the Zammad containers.")
    
    # restart
    subparsers.add_parser("restart", help="Restart the Zammad containers.")
    
    # status
    subparsers.add_parser("status", help="Inspect status of active services.")
    
    # logs
    log_parser = subparsers.add_parser("logs", help="View container logs.")
    log_parser.add_argument("service", nargs="?", default=None, help="Optional specific service (e.g. zammad-nginx, zammad-postgresql)")
    log_parser.add_argument("-f", "--follow", action="store_true", help="Follow logs output in real-time.")
    
    # db subparser
    db_parser = subparsers.add_parser("db", help="Database utilities.")
    db_sub = db_parser.add_subparsers(dest="db_command", help="Database Commands")
    db_sub.add_parser("shell", help="Drop into PostgreSQL CLI psql shell.")
    db_sub.add_parser("info", help="Print credentials and connection guides.")
    
    db_bk_parser = db_sub.add_parser("backup", help="Create database SQL dump.")
    db_bk_parser.add_argument("-f", "--file", default=None, help="Output backup file path.")
    
    db_rst_parser = db_sub.add_parser("restore", help="Restore database from SQL dump.")
    db_rst_parser.add_argument("file", help="Path to SQL dump file.")
    
    # backup subparser
    backup_parser = subparsers.add_parser("backup", help="Volume-based backups.")
    backup_sub = backup_parser.add_subparsers(dest="backup_command", help="Volume Backup Commands")
    backup_sub.add_parser("create", help="Create a compressed full volume-based backup.")
    backup_sub.add_parser("list", help="List available full volume backups.")
    
    backup_rst_parser = backup_sub.add_parser("restore", help="Restore full volumes from backup.")
    backup_rst_parser.add_argument("file", help="Filename of the volume backup.")
    
    # health
    subparsers.add_parser("health", help="Run Zammad health checks.")
    
    # uninstall
    subparsers.add_parser("uninstall", help="Uninstall Zammad stack, teardown containers and delete data.")

    args = parser.parse_args()
    
    if args.command is None:
        run_interactive_menu()
        return

    setup_logging()
    
    try:
        if args.command == "install":
            run_installation()
        elif args.command == "uninstall":
            uninstall_zammad()
        elif args.command == "start":
            start_services()
        elif args.command == "stop":
            stop_services()
        elif args.command == "restart":
            restart_services()
        elif args.command == "status":
            show_status()
        elif args.command == "logs":
            stream_logs(service=args.service, follow=args.follow)
        elif args.command == "health":
            health_check()
        elif args.command == "db":
            if args.db_command == "shell":
                open_db_shell()
            elif args.db_command == "info":
                show_db_info()
            elif args.db_command == "backup":
                backup_db(backup_file=args.file)
            elif args.db_command == "restore":
                restore_db(backup_file=args.file)
            else:
                db_parser.print_help()
        elif args.command == "backup":
            if args.backup_command == "create":
                backup_volumes()
            elif args.backup_command == "list":
                list_backups()
            elif args.backup_command == "restore":
                restore_volumes(args.file)
            else:
                backup_parser.print_help()
        else:
            parser.print_help()
            
    except Exception as e:
        log_error(str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
