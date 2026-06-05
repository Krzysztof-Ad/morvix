/*
 * Exact cover solver (a compact Algorithm X), used as a Morvix example.
 *
 * Input format:
 *   - line 1: a filter, one char per column ('+' = print this column, else hide it)
 *   - then:   matrix rows of the same length ('_' = does not cover, any other
 *             char = covers that column with that symbol)
 *   - a blank line or EOF ends the matrix
 *
 * For every exact cover (a set of rows that covers each column exactly once)
 * the merged row is printed, showing only the '+' columns.
 *
 * This is the kind of program where random input is useless - it needs a
 * structured, solvable instance - which is exactly why the example ships a
 * generator (gen_cover.py).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_COLS 300
#define MAX_ROWS 200

static char filter[MAX_COLS + 2];
static char *matrix[MAX_ROWS];
static int n_cols, n_rows;
static int covered[MAX_COLS];      /* 1 if a column is already covered */
static int chosen[MAX_ROWS];       /* the rows in the current partial solution */

/* A row fits if none of its symbols land on an already-covered column. */
static int fits(const char *row) {
    for (int c = 0; c < n_cols; c++)
        if (row[c] != '_' && covered[c])
            return 0;
    return 1;
}

/* Mark (val=1) or unmark (val=0) the columns a row covers. */
static void mark(const char *row, int val) {
    for (int c = 0; c < n_cols; c++)
        if (row[c] != '_')
            covered[c] = val;
}

/* Pick the uncovered column reachable by the fewest rows; -1 if all covered. */
static int pick_column(void) {
    int best = -1, best_count = MAX_ROWS + 1;
    for (int c = 0; c < n_cols; c++) {
        if (covered[c]) continue;
        int count = 0;
        for (int r = 0; r < n_rows; r++)
            if (matrix[r][c] != '_' && fits(matrix[r]))
                count++;
        if (count < best_count) { best_count = count; best = c; }
    }
    return best;
}

static void print_solution(int depth) {
    char merged[MAX_COLS];
    for (int c = 0; c < n_cols; c++) merged[c] = '_';
    for (int k = 0; k < depth; k++)
        for (int c = 0; c < n_cols; c++)
            if (matrix[chosen[k]][c] != '_')
                merged[c] = matrix[chosen[k]][c];
    for (int c = 0; c < n_cols; c++)
        if (filter[c] == '+')
            putchar(merged[c]);
    putchar('\n');
}

static void solve(int depth) {
    int col = pick_column();
    if (col == -1) { print_solution(depth); return; }
    for (int r = 0; r < n_rows; r++) {
        if (matrix[r][col] != '_' && fits(matrix[r])) {
            chosen[depth] = r;
            mark(matrix[r], 1);
            solve(depth + 1);
            mark(matrix[r], 0);
        }
    }
}

static int read_line(char *buf, int cap) {
    int c, i = 0;
    while ((c = getchar()) != EOF && c != '\n')
        if (i < cap - 1) buf[i++] = (char) c;
    buf[i] = '\0';
    return (c == EOF && i == 0) ? -1 : i;
}

int main(void) {
    n_cols = read_line(filter, sizeof filter);
    if (n_cols <= 0) return 0;
    char line[MAX_COLS + 2];
    while (n_rows < MAX_ROWS && read_line(line, sizeof line) > 0) {
        matrix[n_rows] = malloc((size_t) n_cols + 1);
        memcpy(matrix[n_rows], line, (size_t) n_cols + 1);
        n_rows++;
    }
    solve(0);
    for (int r = 0; r < n_rows; r++) free(matrix[r]);
    return 0;
}
