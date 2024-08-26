from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


setup(
    name="graph-migrate",
    version="0.5",
    author="ALTIBASE",
    author_email="jason.park@altibase.com",
    description="A tool for migrating data from relational database to graph databases",
    long_description=long_description,
    url="https://github.com/jasonpark3306/GraphMigrate",
    packages=find_packages(),
    install_requires=[
        "PyQt6==6.5.2",
        "psycopg2-binary==2.9.7",
        "neo4j==5.11.0",
        "pymongo==4.4.1",
        "pandas==2.0.3",
        "networkx==3.1",
        "matplotlib==3.7.2",
        "pytz==2023.3"
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "graph-migrate=main:main",
        ],
    },
)
