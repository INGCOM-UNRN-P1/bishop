#include <stdlib.h>

typedef struct nodo {
    int dato;
    struct nodo *ant;
    struct nodo *sig;
} Nodo;

int main(void)
{
    Nodo *a = malloc(sizeof(Nodo));
    Nodo *b = malloc(sizeof(Nodo));
    Nodo *c = malloc(sizeof(Nodo));
    a->dato = 1; b->dato = 2; c->dato = 3;
    a->ant = c; a->sig = b;
    b->ant = a; b->sig = c;
    c->ant = b; c->sig = a;
    int **m = malloc(2 * sizeof(int *));
    m[0] = calloc(3, sizeof(int));
    m[1] = calloc(3, sizeof(int));
    m[1][2] = 7;
    int *suelto = malloc(sizeof(int));
    free(suelto);
    Nodo *lista = a;
    return lista->dato + m[1][2];
}
