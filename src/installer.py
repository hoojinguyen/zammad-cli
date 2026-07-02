import os
import shutil
import platform
import subprocess
import secrets
import string
import socket
from src.utils import log_info, log_warn, log_error, log_step, get_install_dir, run_command, Colors
import src.config as config

def check_docker_installed():
    """Verifies that docker is installed and running."""
    try:
        run_command(["docker", "--version"], capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("Docker is not installed or not in PATH. Please run install.sh first.")
    
    try:
        run_command(["docker", "info"], capture_output=True)
    except subprocess.CalledProcessError:
        raise RuntimeError(
            "Docker daemon is not running. Please start Docker (e.g. sudo systemctl start docker, or open Docker Desktop on macOS)."
        )

def is_port_in_use(port):
    """Checks if a port is in use on the host system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            # Bind to all interfaces to test port availability
            s.bind(('', port))
            return False
        except socket.error:
            return True

def check_and_tune_kernel():
    """Checks and configures vm.max_map_count for Elasticsearch on Linux."""
    if platform.system() == "Linux":
        try:
            sysctl_path = "/proc/sys/vm/max_map_count"
            if os.path.exists(sysctl_path):
                with open(sysctl_path, "r") as f:
                    val = int(f.read().strip())
                if val < config.REQUIRED_VM_MAX_MAP_COUNT:
                    log_warn(f"vm.max_map_count is currently {val}. Zammad's Elasticsearch requires at least {config.REQUIRED_VM_MAX_MAP_COUNT}.")
                    log_info("Tuning vm.max_map_count dynamically...")
                    run_command(["sysctl", "-w", f"vm.max_map_count={config.REQUIRED_VM_MAX_MAP_COUNT}"])
                    
                    # Persist it
                    config_path = "/etc/sysctl.conf"
                    if os.path.exists(config_path):
                        with open(config_path, "r") as f:
                            content = f.read()
                        if "vm.max_map_count" not in content:
                            log_info("Persisting vm.max_map_count tuning in /etc/sysctl.conf...")
                            with open(config_path, "a") as f:
                                f.write(f"\n# Required for Elasticsearch (Zammad)\nvm.max_map_count={config.REQUIRED_VM_MAX_MAP_COUNT}\n")
                    log_info("Kernel tuning successfully verified and persisted.")
                else:
                    log_info(f"Kernel parameter vm.max_map_count verified ({val} >= {config.REQUIRED_VM_MAX_MAP_COUNT}).")
        except Exception as e:
            log_warn(f"Failed to verify or tune kernel parameter vm.max_map_count: {e}")
            log_warn(f"Elasticsearch may fail to start. Please run manually: sudo sysctl -w vm.max_map_count={config.REQUIRED_VM_MAX_MAP_COUNT}")

def print_installation_report(reports):
    """Prints a styled summary of all installation step outcomes."""
    print(f"\n{Colors.BOLD}===================================================={Colors.NC}")
    print(f"{Colors.BOLD}            Zammad Installation Report{Colors.NC}")
    print(f"{Colors.BOLD}===================================================={Colors.NC}")
    
    any_failed = False
    for step_name, status, details in reports:
        if status == "SUCCESS":
            status_text = f"{Colors.GREEN}[SUCCESS]{Colors.NC}"
        elif status == "SKIPPED":
            status_text = f"{Colors.YELLOW}[SKIPPED]{Colors.NC}"
        else:
            status_text = f"{Colors.RED}[FAILED]{Colors.NC}"
            any_failed = True
            
        print(f"  {status_text:<19} {step_name}")
        if details:
            print(f"      Note: {Colors.CYAN}{details}{Colors.NC}")
            
    print(f"{Colors.BOLD}===================================================={Colors.NC}")
    
    if any_failed:
        log_path = os.path.abspath(os.path.join(get_install_dir(), "zammad-install.log"))
        log_error(f"Installation failed. Please review the trace and detailed logs at:\n  {Colors.BLUE}{log_path}{Colors.NC}")
    else:
        log_info("Zammad installation completed successfully. Services are starting!")

def run_installation():
    """Main installer orchestration workflow."""
    install_dir = get_install_dir()
    log_step(f"Starting Zammad installation in {install_dir}")
    
    reports = []
    
    try:
        # 1. Docker Daemon Check
        try:
            check_docker_installed()
            reports.append(("Docker Daemon Check", "SUCCESS", "Docker is running"))
        except Exception as e:
            reports.append(("Docker Daemon Check", "FAILED", str(e)))
            raise e
            
        # 2. Kernel Tuning
        try:
            check_and_tune_kernel()
            reports.append(("Kernel Parameter Check", "SUCCESS", f"vm.max_map_count >= {config.REQUIRED_VM_MAX_MAP_COUNT}"))
        except Exception as e:
            reports.append(("Kernel Parameter Check", "FAILED", str(e)))
            raise e

        # 3. Clone Repository
        os.makedirs(install_dir, exist_ok=True)
        os.chdir(install_dir)
        
        if not os.path.exists(os.path.join(install_dir, "docker-compose.yml")):
            try:
                log_info("Cloning Zammad Docker Compose repository...")
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    run_command(["git", "clone", config.ZAMMAD_COMPOSE_REPO, tmpdir])
                    # Copy contents to install_dir
                    for item in os.listdir(tmpdir):
                        s = os.path.join(tmpdir, item)
                        d = os.path.join(install_dir, item)
                        if os.path.isdir(s):
                            if item != ".git":
                                shutil.copytree(s, d, dirs_exist_ok=True)
                        else:
                            shutil.copy2(s, d)
                reports.append(("Clone Zammad Repository", "SUCCESS", "Cloned successfully"))
            except Exception as e:
                reports.append(("Clone Zammad Repository", "FAILED", str(e)))
                raise e
        else:
            reports.append(("Clone Zammad Repository", "SKIPPED", "docker-compose.yml already exists"))

        # 4. Handle Permissions (Linux specific)
        sudo_user = os.environ.get("SUDO_USER")
        if platform.system() == "Linux" and sudo_user:
            try:
                log_info(f"Adjusting folder ownership for user: {sudo_user}")
                run_command(["chown", "-R", f"{sudo_user}:{sudo_user}", install_dir])
                reports.append(("Configure Directory Permissions", "SUCCESS", f"Owner set to {sudo_user}"))
            except Exception as e:
                reports.append(("Configure Directory Permissions", "FAILED", str(e)))
                raise e
        else:
            reports.append(("Configure Directory Permissions", "SKIPPED", "Not on Linux/Ubuntu or running as normal user"))

        # 5. Environment Generation and Port Checking
        env_path = os.path.join(install_dir, ".env")
        env_dist_path = os.path.join(install_dir, ".env.dist")
        
        # If .env exists but is empty or missing POSTGRES_PASS, wipe and regenerate
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                content = f.read()
            if "POSTGRES_PASS=" in content and ("POSTGRES_PASS=\n" in content or content.endswith("POSTGRES_PASS=")):
                log_warn("Detected .env with empty POSTGRES_PASS. Re-generating...")
                os.remove(env_path)
                
        if not os.path.exists(env_path):
            try:
                shutil.copyfile(env_dist_path, env_path)
                
                # Generate credentials
                alphabet = string.ascii_letters + string.digits
                db_password = ''.join(secrets.choice(alphabet) for _ in range(24))
                db_user = config.DB_DEFAULT_USER
                
                # Port Collision Check: scan ports starting from configured default
                web_port = config.DEFAULT_WEB_PORT
                while is_port_in_use(web_port):
                    log_warn(f"Port {web_port} is already in use on the host.")
                    web_port += 1
                
                log_info(f"Port checking complete. Selecting host port {web_port} for Zammad web interface.")
                
                with open(env_path, "r") as f:
                    lines = f.readlines()
                    
                new_lines = []
                for line in lines:
                    if line.startswith("POSTGRES_PASS="):
                        new_lines.append(f"POSTGRES_PASS={db_password}\n")
                    elif line.startswith("POSTGRES_USER="):
                        new_lines.append(f"POSTGRES_USER={db_user}\n")
                    elif line.startswith("NGINX_PORT="):
                        new_lines.append(f"NGINX_PORT={config.DEFAULT_WEB_PORT}\n")
                    elif line.startswith("NGINX_EXPOSE_PORT="):
                        new_lines.append(f"NGINX_EXPOSE_PORT={web_port}\n")
                    else:
                        # Handle commented defaults
                        if line.strip().startswith("# POSTGRES_PASS="):
                            new_lines.append(f"POSTGRES_PASS={db_password}\n")
                        elif line.strip().startswith("# POSTGRES_USER="):
                            new_lines.append(f"POSTGRES_USER={db_user}\n")
                        elif line.strip().startswith("# NGINX_PORT="):
                            new_lines.append(f"NGINX_PORT={config.DEFAULT_WEB_PORT}\n")
                        elif line.strip().startswith("# NGINX_EXPOSE_PORT="):
                            new_lines.append(f"NGINX_EXPOSE_PORT={web_port}\n")
                        else:
                            new_lines.append(line)
                            
                with open(env_path, "w") as f:
                    f.writelines(new_lines)
                    
                reports.append(("Generate .env & DB Passwords", "SUCCESS", f"Web Port: {web_port}"))
            except Exception as e:
                reports.append(("Generate .env & DB Passwords", "FAILED", str(e)))
                raise e
        else:
            # Check if port in existing .env is currently in use
            try:
                from src.db import parse_config_env
                cfg = parse_config_env()
                configured_port = int(cfg.get("NGINX_EXPOSE_PORT", config.DEFAULT_WEB_PORT))
                if is_port_in_use(configured_port):
                    log_warn(f"WARNING: Port {configured_port} configured in .env is currently in use! Startup might fail.")
                reports.append(("Generate .env & DB Passwords", "SKIPPED", f"Existing .env checked (Port: {configured_port})"))
            except Exception:
                reports.append(("Generate .env & DB Passwords", "SKIPPED", ".env already exists"))

        # 6. Start containers
        try:
            log_step("Starting Zammad Docker container stack...")
            try:
                run_command(["docker", "compose", "down", "-v", "--remove-orphans"])
            except Exception:
                pass
            run_command(["docker", "compose", "up", "-d"])
            reports.append(("Start Zammad Containers", "SUCCESS", "All services active"))
        except Exception as e:
            reports.append(("Start Zammad Containers", "FAILED", str(e)))
            raise e

        # Print successful report
        print_installation_report(reports)

    except Exception as e:
        print_installation_report(reports)
        raise e

def uninstall_zammad():
    """Stops containers, deletes volumes, deletes installation directory and symlinks."""
    install_dir = get_install_dir()
    log_warn(f"WARNING: This will completely delete Zammad from {install_dir} including all database data and configurations!")
    confirm = input("Are you sure you want to uninstall and wipe all Zammad data? (y/N): ").strip().lower()
    if confirm not in ['y', 'yes']:
        log_info("Uninstall cancelled.")
        return

    log_step("Tearing down Docker container stack...")
    os.chdir(install_dir)
    try:
        run_command(["docker", "compose", "down", "-v", "--remove-orphans"])
    except Exception as e:
        log_warn(f"Warning during compose down: {e}")

    # Remove global symlink
    symlink_path = "/usr/local/bin/zammad"
    if os.path.exists(symlink_path):
        log_info(f"Removing global symlink: {symlink_path}")
        try:
            os.remove(symlink_path)
        except Exception as e:
            log_warn(f"Failed to remove symlink (might need root/sudo): {e}")

    # Clean files
    if platform.system() == "Linux" and install_dir == "/opt/zammad-docker":
        log_info(f"Removing installation directory: {install_dir}")
        try:
            shutil.rmtree(install_dir)
        except Exception as e:
            log_warn(f"Failed to delete directory {install_dir}: {e}. You can delete it manually.")
    else:
        # Delete generated files to keep the repo clean
        log_info("Removing Zammad configuration and data...")
        generated_items = [
            ".env",
            "zammad-install.log",
            "backups",
            "docker-compose.yml",
            ".env.dist",
            "docker-compose.override.yml",
            "scenarios"
        ]
        for item in generated_items:
            path = os.path.join(install_dir, item)
            if os.path.exists(path):
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception as e:
                    log_warn(f"Failed to delete {path}: {e}")
                    
    log_info("Zammad has been successfully uninstalled.")
