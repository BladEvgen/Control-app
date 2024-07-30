import os
import glob
import subprocess

max_line_length = 100
directories_to_format = [
    "\\backend\\monitoring_app",
]


def run_autopep8(file_path):
    """Run autopep8 on a single file."""
    subprocess.run(
        [
            "autopep8",
            "--in-place",
            "--aggressive",
            "--aggressive",
            f"--max-line-length={max_line_length}",
            file_path,
        ]
    )


def run_yapf(file_path):
    """Run yapf on a single file."""
    subprocess.run(
        [
            "yapf",
            "--in-place",
            f"--style={{based_on_style: pep8, column_limit: {max_line_length}}}",
            file_path,
        ]
    )


def run_flake8(file_path):
    """Run flake8 on a single file."""
    result = subprocess.run(["flake8", file_path], capture_output=True, text=True)
    return result.stdout


def format_code_in_directory(directory):
    """Format all Python files in the given directory."""
    for file_path in glob.glob(os.path.join(directory, "**", "*.py"), recursive=True):
        print(f"Formatting {file_path}")
        run_autopep8(file_path)
        run_yapf(file_path)
        flake8_output = run_flake8(file_path)
        if flake8_output:
            print(f"flake8 output for {file_path}:\n{flake8_output}")
            print("Consider manually fixing these remaining issues.")


def main():
    for directory in directories_to_format:
        format_code_in_directory(directory)


if __name__ == "__main__":
    main()
