"""This is a test file to test the idea of monitoring the WindowServer process"""

import time

import psutil


def find_windowserver():
    for proc in psutil.process_iter(["pid", "name"]):
        if proc.info["name"] == "WindowServer":
            return proc
    return None


def monitor():
    proc = find_windowserver()

    if not proc:
        print("WindowServer no encontrado")
        return

    print(f"Monitorizando WindowServer (PID: {proc.pid})...\n")

    while True:
        try:
            cpu = proc.cpu_percent(interval=1)
            mem = proc.memory_info().rss / (1024 * 1024)  # MB

            print(f"CPU: {cpu:.2f}% | RAM: {mem:.2f} MB")

        except psutil.NoSuchProcess:
            print("El proceso ha terminado")
            break


if __name__ == "__main__":
    monitor()
