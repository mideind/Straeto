echo "Prepare and upload a new Straeto version"
rm -rf build/
rm -rf dist/
python setup.py bdist_wheel --universal
python setup.py sdist
twine upload dist/straeto-$1*

