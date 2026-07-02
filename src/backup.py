import os
import datetime
import subprocess
import shutil
import json
from src.utils import log_info, log_warn, log_error, get_install_dir, run_command, Colors

def get_backup_dir():
    """Returns the backup directory path."""
    install_dir = get_install_dir()
    backup_dir = os.path.join(install_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir

def list_backups():
    """Lists all available full volume backups."""
    backup_dir = get_backup_dir()
    log_info("Available full volume backups:")
    print("")
    
    try:
        files = [f for f in os.listdir(backup_dir) if f.startswith("zammad-backup-") and f.endswith(".tar.gz")]
    except Exception:
        files = []
        
    if not files:
        print("  No volume backups found.")
        print("")
        return
        
    for f in sorted(files):
        path = os.path.join(backup_dir, f)
        size_bytes = os.path.getsize(path)
        size_str = f"{size_bytes / (1024*1024):.2f} MB"
        print(f"  - {f} ({size_str})")
    print("")

def get_compose_project_name():
    """Queries Docker Compose for the current project name."""
    install_dir = get_install_dir()
    try:
        # Run docker compose config and get the project name
        stdout, _ = run_command(["docker", "compose", "config", "--format", "json"], cwd=install_dir, capture_output=True)
        data = json.loads(stdout)
        if "name" in data:
            return data["name"]
    except Exception:
        pass
    # Fallback to normalized directory name
    return os.path.basename(install_dir).lower().replace("_", "").replace("-", "")

def backup_volumes():
    """Performs a full volume-based backup of Zammad data."""
    install_dir = get_install_dir()
    backup_dir = get_backup_dir()
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"zammad-backup-{timestamp}.tar.gz")
    
    log_info(f"Starting full volume-based backup to: {backup_file}")
    
    project_name = get_compose_project_name()
    
    log_warn("It is highly recommended to stop services before backup to ensure database and search index consistency.")
    confirm = input("Stop Zammad services now for a clean backup? (y/N): ").strip().lower()
    services_stopped = False
    
    if confirm in ['y', 'yes']:
        from src.manager import stop_services
        try:
            stop_services()
            services_stopped = True
        except Exception as e:
            log_error(f"Failed to stop services: {e}")
            
    try:
        # Run a temporary alpine container to archive the volumes
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{project_name}_postgresql-data:/data/postgresql",
            "-v", f"{project_name}_elasticsearch-data:/data/elasticsearch",
            "-v", f"{project_name}_redis-data:/data/redis",
            "-v", f"{project_name}_zammad-storage:/data/storage",
            "-v", f"{backup_dir}:/backup",
            "alpine", "tar", "czf", f"/backup/zammad-backup-{timestamp}.tar.gz", "-C", "/data", "."
        ]
        
        log_info("Archiving Docker volumes...")
        run_command(cmd, cwd=install_dir)
        
        size_bytes = os.path.getsize(backup_file)
        size_mb = size_bytes / (1024 * 1024)
        log_info(f"Backup completed successfully. Size: {size_mb:.2f} MB")
        log_info(f"Backup file: {backup_file}")
    except Exception as e:
        log_error(f"Backup failed: {e}")
    finally:
        if services_stopped:
            log_info("Restarting Zammad services...")
            from src.manager import start_services
            try:
                start_services()
            except Exception as e:
                log_error(f"Failed to restart services: {e}")

def restore_volumes(backup_filename):
    """Restores Zammad volumes from a compressed gzip archive."""
    install_dir = get_install_dir()
    backup_dir = get_backup_dir()
    
    # Resolve absolute path of backup file
    if os.path.isabs(backup_filename):
        backup_file = backup_filename
    else:
        backup_file = os.path.join(backup_dir, backup_filename)
        
    if not os.path.exists(backup_file):
        log_error(f"Backup file not found: {backup_file}")
        return
        
    log_warn(f"WARNING: Restoring from backup '{os.path.basename(backup_file)}' will completely OVERWRITE your current database and files!")
    confirm = input("Are you absolutely sure you want to proceed? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        log_info("Restore cancelled.")
        return
        
    project_name = get_compose_project_name()
    
    log_info("Stopping containers before restore...")
    from src.manager import stop_services
    try:
        stop_services()
    except Exception as e:
        log_warn(f"Could not stop services: {e}. Attempting restore anyway...")
        
    try:
        # Run a temporary alpine container to clear and extract volumes
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{project_name}_postgresql-data:/data/postgresql",
            "-v", f"{project_name}_elasticsearch-data:/data/elasticsearch",
            "-v", f"{project_name}_redis-data:/data/redis",
            "-v", f"{project_name}_zammad-storage:/data/storage",
            "-v", f"{os.path.dirname(backup_file)}:/backup",
            "alpine", "sh", "-c",
            f"rm -rf /data/postgresql/* /data/elasticsearch/* /data/redis/* /data/storage/* && tar xzf /backup/{os.path.basename(backup_file)} -C /data"
        ]
        
        log_info("Restoring Docker volumes from archive...")
        run_command(cmd, cwd=install_dir)
        log_info("Volume restore completed successfully!")
    except Exception as e:
        log_error(f"Restore failed: {e}")
    finally:
        log_info("Restarting Zammad services...")
        from src.manager import start_services
        try:
            start_services()
        except Exception as e:
            log_error(f"Failed to restart services: {e}")
