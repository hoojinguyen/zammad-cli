import os
import sys
import platform
import subprocess
import logging

class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    CYAN = '\033[0;36m'
    BLUE = '\033[0;34m'
    BOLD = '\033[1m'
    NC = '\033[0m'

def get_install_dir():
    """Returns the installation directory based on the OS, or override via env var."""
    env_override = os.environ.get("ZAMMAD_INSTALL_DIR")
    if env_override:
        return os.path.abspath(env_override)
    
    if platform.system() == "Linux":
        return "/opt/zammad-docker"
    else:
        # Parent of the src/ directory
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def setup_logging():
    """Configures logging to write to zammad-install.log in the installation directory."""
    install_dir = get_install_dir()
    os.makedirs(install_dir, exist_ok=True)
    log_path = os.path.join(install_dir, "zammad-install.log")
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_path, mode='a', encoding='utf-8')
        ]
    )

def log_info(msg):
    logging.info(msg)
    if sys.stdout.isatty():
        print(f"{Colors.GREEN}[INFO]{Colors.NC} {msg}")
    else:
        print(f"[INFO] {msg}")

def log_warn(msg):
    logging.warning(msg)
    if sys.stdout.isatty():
        print(f"{Colors.YELLOW}[WARN]{Colors.NC} {msg}")
    else:
        print(f"[WARN] {msg}")

def log_error(msg):
    logging.error(msg)
    if sys.stderr.isatty():
        print(f"{Colors.RED}[ERROR]{Colors.NC} {Colors.BOLD}{msg}{Colors.NC}", file=sys.stderr)
    else:
        print(f"[ERROR] {msg}", file=sys.stderr)

def log_step(msg):
    logging.info(f"STEP: {msg}")
    if sys.stdout.isatty():
        print(f"\n{Colors.CYAN}{Colors.BOLD}=== {msg} ==={Colors.NC}")
    else:
        print(f"\n=== {msg} ===")

def check_docker_permission_error(output_str):
    """Checks for Docker socket permission issues and prints a helpful guide."""
    if "permission denied" in output_str.lower() and "docker.sock" in output_str.lower():
        log_warn("DOCKER SOCKET ACCESS DENIED: Your current shell session does not have permission to access Docker.")
        log_warn("Please run 'newgrp docker' in your terminal, or log out and log back in, to apply group changes.")

def run_command(cmd, cwd=None, shell=False, capture_output=False, show_output=False):
    """
    Executes a shell command. Logs all output to the installation log file in real-time.
    If capture_output is True, returns (stdout, stderr).
    If show_output is True, streams the output in real-time to stdout.
    If the command exits with non-zero status, raises a subprocess.CalledProcessError.
    """
    logging.info(f"Running command: {cmd if isinstance(cmd, str) else ' '.join(cmd)} (cwd={cwd})")
    
    # We always redirect stderr to stdout to preserve ordering in the logs, unless we need separate capture
    if capture_output:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            shell=shell,
            text=True,
            capture_output=True
        )
        # Write captured output to log file
        if result.stdout:
            for line in result.stdout.splitlines():
                logging.info(f"[CMD-OUT] {line}")
        if result.stderr:
            for line in result.stderr.splitlines():
                logging.warning(f"[CMD-ERR] {line}")
        
        if result.returncode != 0:
            logging.error(f"Command failed with exit code {result.returncode}")
            combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
            check_docker_permission_error(combined_output)
            raise subprocess.CalledProcessError(
                result.returncode, cmd, output=result.stdout, stderr=result.stderr
            )
        return result.stdout.strip(), result.stderr.strip()
    
    # Otherwise stream directly to the logger in real-time
    p = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    output_lines = []
    if p.stdout:
        for line in p.stdout:
            stripped = line.rstrip('\n')
            logging.info(f"[CMD] {stripped}")
            output_lines.append(stripped)
            if show_output:
                print(stripped)
                sys.stdout.flush()
            
    p.wait()
    
    if p.returncode != 0:
        logging.error(f"Command failed with exit code {p.returncode}")
        # Print the last few lines of the output to console for immediate visibility
        err_snippet = "\n".join(output_lines[-10:]) if output_lines else "No output"
        if sys.stderr.isatty():
            print(f"{Colors.RED}{Colors.BOLD}Last 10 lines of command output:{Colors.NC}\n{err_snippet}", file=sys.stderr)
        else:
            print(f"Last 10 lines of command output:\n{err_snippet}", file=sys.stderr)
            
        check_docker_permission_error("\n".join(output_lines))
        raise subprocess.CalledProcessError(
            p.returncode, cmd, output="\n".join(output_lines)
        )
        
    return "\n".join(output_lines), ""
