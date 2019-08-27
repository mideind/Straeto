echo "Prepare and upload a new Straeto version"
python setup.py bdist_wheel --universal
python setup.py sdist
twine upload dist/straeto-$1*

