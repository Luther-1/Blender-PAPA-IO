gcc -shared -O3 -c texture.c -o texture.o
gcc -shared -o PTex.dll texture.o
del texture.o

gcc -O3 -fPIC -fopenmp -Wall -c -o texture.o texture_extensions.c
gcc -shared -fPIC -o ETex.dll texture.o -lgomp -static
del texture.o

rem gcc -O3 -fPIC -fopenmp -Wall -lgomp -g -o main.exe main.c
pause