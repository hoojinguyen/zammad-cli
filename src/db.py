import os
import sys
import subprocess
import datetime
from src.utils import log_info, log_warn, log_error, get_install_dir, Colors
import src.config as config

def parse_config_env():
    """Parses .env and returns its variables as a dictionary."""
    install_dir = get_install_dir()
    config_path = os.path.join(install_dir, ".env")
    if not os.path.exists(config_path):
        raise RuntimeError(".env not found. Please install Zammad first.")
    
    config = {}
    with open(config_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                config[key.strip()] = val.strip()
    return config

def get_db_credentials():
    """Extracts database credentials from the .env file."""
    env_config = parse_config_env()
    db_user = env_config.get("POSTGRES_USER", config.DB_DEFAULT_USER)
    db_pass = env_config.get("POSTGRES_PASS")
    db_name = env_config.get("POSTGRES_DB", config.DB_DEFAULT_NAME)
    db_host = "127.0.0.1"
    db_port = "5432"
    
    if not db_pass:
        raise ValueError("POSTGRES_PASS is not set in .env.")
        
    return db_host, db_port, db_user, db_pass, db_name

def open_db_shell():
    """Opens an interactive PostgreSQL shell inside the db container."""
    install_dir = get_install_dir()
    os.chdir(install_dir)
    
    try:
        _, _, user, password, db_name = get_db_credentials()
    except Exception as e:
        log_error(str(e))
        return
        
    log_info("Opening database interactive shell... (Type '\\q' to quit)")
    
    cmd = [
        "docker", "compose", "exec", "-it", "zammad-postgresql",
        "env", f"PGPASSWORD={password}", "psql", "-U", user, "-d", db_name
    ]
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nExiting shell.")

def show_db_info():
    """Displays connection details and instructions for external database tools."""
    try:
        host, port, user, password, db_name = get_db_credentials()
    except Exception as e:
        log_error(str(e))
        return

    print(f"\n{Colors.BOLD}===================================================={Colors.NC}")
    print(f"{Colors.BOLD}            Database Connection Guide{Colors.NC}")
    print(f"{Colors.BOLD}===================================================={Colors.NC}")
    print(f"  Database Host:     {Colors.CYAN}{host}{Colors.NC} (from local host machine)")
    print(f"  Database Port:     {Colors.CYAN}{port}{Colors.NC}")
    print(f"  Database Name:     {Colors.CYAN}{db_name}{Colors.NC}")
    print(f"  Database Username: {Colors.CYAN}{user}{Colors.NC}")
    print(f"  Database Password: {Colors.YELLOW}{password}{Colors.NC}")
    print(f"----------------------------------------------------")
    print(f"How to Connect via CLI (from host):")
    print(f"  PGPASSWORD='{password}' psql -h {host} -p {port} -U {user} -d {db_name}")
    print(f"\nHow to Connect via CLI (via Docker CLI wrapper):")
    print(f"  ./zammad db shell")
    print(f"\nHow to Connect via GUI Tool (DBeaver / TablePlus):")
    print(f"  1. Set Connection Type to PostgreSQL.")
    print(f"  2. Server Host: 127.0.0.1  |  Port: 5432")
    print(f"  3. Database: {db_name}  |  Username: {user}")
    print(f"  4. Password: {password}")
    print(f"  Note: Ensure the 'zammad-postgresql' container is active.")
    print(f"{Colors.BOLD}===================================================={Colors.NC}\n")

def backup_db(backup_file=None):
    """Creates a SQL dump backup of the database on the host machine."""
    install_dir = get_install_dir()
    os.chdir(install_dir)
    
    try:
        _, _, user, password, db_name = get_db_credentials()
    except Exception as e:
        log_error(str(e))
        return

    if not backup_file:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(install_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"zammad_db_backup_{timestamp}.sql")
    else:
        backup_file = os.path.abspath(backup_file)

    log_info(f"Creating database SQL dump... saving to {backup_file}")
    
    cmd = f"docker compose exec -T zammad-postgresql env PGPASSWORD='{password}' pg_dump -U {user} {db_name} > '{backup_file}'"
    
    try:
        subprocess.run(cmd, shell=True, check=True)
        log_info(f"Database backup created successfully: {backup_file}")
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to create database backup: {e}")

def restore_db(backup_file):
    """Restores a database SQL dump backup into the container db."""
    install_dir = get_install_dir()
    os.chdir(install_dir)
    
    if not os.path.exists(backup_file):
        log_error(f"Backup file not found: {backup_file}")
        return

    try:
        _, _, user, password, db_name = get_db_credentials()
    except Exception as e:
        log_error(str(e))
        return

    log_warn(f"WARNING: Restoring database from {backup_file} will overwrite the current database!")
    confirm = input("Are you sure you want to continue? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        log_info("Database restore cancelled.")
        return

    log_info(f"Restoring database from {backup_file}...")
    
    cmd = f"docker compose exec -T zammad-postgresql env PGPASSWORD='{password}' psql -U {user} -d {db_name} < '{backup_file}'"
    
    try:
        subprocess.run(cmd, shell=True, check=True)
        log_info("Database restored successfully.")
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to restore database: {e}")

def show_env_config():
    """Prints all active (uncommented) configuration settings in the .env file."""
    try:
        config_data = parse_config_env()
    except Exception as e:
        log_error(str(e))
        return
        
    print(f"\n{Colors.BOLD}===================================================={Colors.NC}")
    print(f"{Colors.BOLD}            Zammad Active Configurations            {Colors.NC}")
    print(f"{Colors.BOLD}===================================================={Colors.NC}")
    for key, val in sorted(config_data.items()):
        if "PASS" in key or "SECRET" in key:
            val_masked = val[:3] + "*" * (len(val) - 3) if len(val) > 3 else "*" * len(val)
            print(f"  {key:<25}: {Colors.YELLOW}{val_masked}{Colors.NC}")
        else:
            print(f"  {key:<25}: {Colors.GREEN}{val}{Colors.NC}")
    print(f"{Colors.BOLD}===================================================={Colors.NC}\n")

def set_env_variable(key, value):
    """Sets a variable in the .env file, updating it if it exists or appending it."""
    install_dir = get_install_dir()
    env_path = os.path.join(install_dir, ".env")
    if not os.path.exists(env_path):
        log_error(f".env not found in {install_dir}. Please run install first.")
        return
        
    key_upper = key.upper()
    key_map = {
        "PORT": "NGINX_EXPOSE_PORT",
        "DB_USER": "POSTGRES_USER",
        "DB_PASS": "POSTGRES_PASS",
        "DB_NAME": "POSTGRES_DB"
    }
    target_key = key_map.get(key_upper, key_upper)
    
    with open(env_path, "r") as f:
        lines = f.readlines()
        
    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{target_key}=") or stripped.startswith(f"# {target_key}=") or stripped.startswith(f"#  {target_key}="):
            new_lines.append(f"{target_key}={value}\n")
            updated = True
        else:
            new_lines.append(line)
            
    if not updated:
        new_lines.append(f"\n{target_key}={value}\n")
        
    try:
        with open(env_path, "w") as f:
            f.writelines(new_lines)
        print(f"Successfully set {Colors.CYAN}{target_key}{Colors.NC} to {Colors.GREEN}{value}{Colors.NC} in .env.")
        print(f"Please restart Zammad services ({Colors.BOLD}zammad restart{Colors.NC}) to apply changes.")
    except Exception as e:
        log_error(f"Failed to update .env file: {e}")
