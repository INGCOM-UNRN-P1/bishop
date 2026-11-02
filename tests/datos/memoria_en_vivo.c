#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct nodo {
    int dato;
    struct nodo *sig;
} nodo_t;

int main(void)
{
    nodo_t *lista = NULL;
    for (int i = 0; i < 3; i++) {
        nodo_t *n = malloc(sizeof(nodo_t));
        n->dato = i;
        n->sig = lista;
        lista = n;
    }
    printf("lista armada\n");
    char *copia = strdup("hola");
    int *v = malloc(2 * sizeof(int));
    v = realloc(v, 100 * sizeof(int));
    v = malloc(sizeof(int));
    free(copia);
    return lista->dato;
}
