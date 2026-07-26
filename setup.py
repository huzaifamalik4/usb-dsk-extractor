from setuptools import setup, find_packages

setup(
    name="usb-dsk-extractor",
    version="1.0.0",
    description="Recover files from raw USB disk images (.dsk, .dd, .img, .bin)",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="USB DSK Extractor",
    url="https://github.com/yourusername/usb-dsk-extractor",
    py_modules=["usb_dsk_extractor"],
    install_requires=["pytsk3>=20231007"],
    entry_points={
        "console_scripts": [
            "usb-dsk-extractor=usb_dsk_extractor:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: System :: Recovery",
        "Intended Audience :: End Users/Desktop",
    ],
    python_requires=">=3.8",
)
