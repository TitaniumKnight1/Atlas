import subprocess
import sys

try:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "C:\\Users\\Ryan\\projects\\Atlas\\tests\\unit\\telemetry\\test_sanitizer_adversarial.py", "-v"],
        capture_output=True,
        text=True,
        cwd="C:\\Users\\Ryan\\projects\\Atlas"
    )
    with open("C:\\Users\\Ryan\\projects\\Atlas\\pytest_output.txt", "w") as f:
        f.write(result.stdout)
        f.write("\n---\n")
        f.write(result.stderr)
except Exception as e:
    with open("C:\\Users\\Ryan\\projects\\Atlas\\pytest_output.txt", "w") as f:
        f.write(str(e))
