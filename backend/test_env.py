import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

print(f"Test Python executable: {sys.executable}")
print(f"Test Python sys.path: {sys.path}")
print(f"Test sys.version: {sys.version}")

try:
    import sentinelhub
    print(f"sentinelhub imported successfully. Version: {sentinelhub.__version__}")
except ImportError:
    print("sentinelhub could not be imported.")
except Exception as e:
    print(f"Error importing sentinelhub: {e}")