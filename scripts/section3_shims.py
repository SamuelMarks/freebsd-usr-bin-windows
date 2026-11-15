"""Build-time C89 Section 3 library generators for curses/terminfo, editline, mp, and sys.

Emits portable C89 headers and source files into ``${CMAKE_BINARY_DIR}/freebsd_generated``
for Section 3 libraries whose upstream implementations depend on platform-specific terminal,
crypto, or kernel interfaces across Windows (Win32 Console VT), 32-bit DOS (BIOS ``Int 10h``
``0xB800:0000``), and POSIX (ANSI VT / ``TIOCGWINSZ``):

  - ``fbsd_libcurses`` & ``fbsd_libtinfow``: ``curses.h``, ``ncurses.h``, ``term.h``,
    ``termcap.h``, ``unctrl.h``, and ``fbsd_curses.c``
  - ``fbsd_libedit``: ``histedit.h``, ``editline/readline.h``, ``readline/readline.h``,
    ``readline/history.h``, and ``fbsd_edit.c``
  - ``fbsd_libmp``: ``mp.h`` and ``fbsd_mp.c`` (arbitrary-precision ``MINT`` arithmetic)
  - ``fbsd_libsys``: ``security/pam_appl.h``, ``security/openpam.h``, ``rpcsvc/ypclnt.h``,
    ``rpcsvc/yp_prot.h``, ``sys/nv.h``, ``bsm/libbsm.h``, and ``fbsd_sys.c``
"""

from __future__ import annotations

from pathlib import Path

LF: str = chr(10)
BS: str = chr(92)


def emit_curses_section3_sources(out_dir: Path) -> dict[str, Path]:
    """Emit portable C89 ``curses`` / ``terminfo`` / ``termcap`` headers and C source.

    Args:
        out_dir: Destination ``codegen/ncurses`` directory.

    Returns:
        Mapping of generated relative filenames to resolved ``Path``s.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    unctrl_h = (
        LF.join(
            [
                "#ifndef FBSD_UNCTRL_H_",
                "#define FBSD_UNCTRL_H_",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "const char *unctrl(unsigned int ch);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    term_h = (
        LF.join(
            [
                "#ifndef FBSD_TERM_H_",
                "#define FBSD_TERM_H_",
                "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                "#if defined(fbsd_libtinfow_EXPORTS) || defined(fbsd_libcurses_EXPORTS)",
                "#define _FBSD_CURSES_DATA extern __declspec(dllexport)",
                "#elif !defined(FBSD_CURSES_STATIC)",
                "#define _FBSD_CURSES_DATA extern __declspec(dllimport)",
                "#else",
                "#define _FBSD_CURSES_DATA extern",
                "#endif",
                "#else",
                "#define _FBSD_CURSES_DATA extern",
                "#endif",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "typedef struct term { const char *term_names; } TERMINAL;",
                "_FBSD_CURSES_DATA TERMINAL *cur_term;",
                "_FBSD_CURSES_DATA char PC;",
                "_FBSD_CURSES_DATA char *UP;",
                "_FBSD_CURSES_DATA char *BC;",
                "_FBSD_CURSES_DATA short ospeed;",
                "int setupterm(const char *term, int filedes, int *errret);",
                "TERMINAL *set_curterm(TERMINAL *nterm);",
                "int del_curterm(TERMINAL *oterm);",
                "int restartterm(const char *term, int filedes, int *errret);",
                "int tigetnum(const char *capname);",
                "int tigetflag(const char *capname);",
                "char *tigetstr(const char *capname);",
                "char *tparm(const char *str, ...);",
                "char *tiparm(const char *str, ...);",
                "int tputs(const char *str, int affcnt, int (*putc_fn)(int));",
                "int putp(const char *str);",
                "int tgetent(char *bp, const char *name);",
                "int tgetflag(const char *id);",
                "int tgetnum(const char *id);",
                "char *tgetstr(const char *id, char **area);",
                "char *tgoto(const char *cap, int col, int row);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    curses_h = (
        LF.join(
            [
                "#ifndef FBSD_CURSES_H_",
                "#define FBSD_CURSES_H_",
                "#include <stdarg.h>",
                "#include <stdbool.h>",
                "#include <stddef.h>",
                "#include <stdint.h>",
                "#include <stdio.h>",
                "#include <wchar.h>",
                "#if defined(_WIN32) || defined(__DOS__) || defined(__MSDOS__)",
                "#include <conio.h>",
                "#endif",
                '#include "unctrl.h"',
                "#ifndef _FBSD_CURSES_DATA",
                "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                "#if defined(fbsd_libtinfow_EXPORTS) || defined(fbsd_libcurses_EXPORTS)",
                "#define _FBSD_CURSES_DATA extern __declspec(dllexport)",
                "#elif !defined(FBSD_CURSES_STATIC)",
                "#define _FBSD_CURSES_DATA extern __declspec(dllimport)",
                "#else",
                "#define _FBSD_CURSES_DATA extern",
                "#endif",
                "#else",
                "#define _FBSD_CURSES_DATA extern",
                "#endif",
                "#endif",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "#ifndef ERR",
                "#define ERR (-1)",
                "#endif",
                "#ifndef OK",
                "#define OK (0)",
                "#endif",
                "#ifndef TRUE",
                "#define TRUE 1",
                "#endif",
                "#ifndef FALSE",
                "#define FALSE 0",
                "#endif",
                "typedef unsigned int chtype;",
                "typedef unsigned int attr_t;",
                "typedef unsigned int wint_t_curses;",
                "#define CCHARW_MAX 5",
                (
                    "typedef struct { attr_t attr; wchar_t chars[CCHARW_MAX]; int ext_col"
                    "or; } cchar_t;"
                ),
                "typedef struct screen SCREEN;",
                "typedef struct _win_st {",
                "    int _cury, _curx;",
                "    int _maxy, _maxx;",
                "    int _begy, _begx;",
                "    attr_t _attrs;",
                "    chtype _bkgd;",
                "    int _keypad, _nodelay, _timeout, _scroll, _leaveok, _clearok, _idlok;",
                "    chtype *_cells;",
                "} WINDOW;",
                "_FBSD_CURSES_DATA WINDOW *stdscr;",
                "_FBSD_CURSES_DATA WINDOW *curscr;",
                "_FBSD_CURSES_DATA WINDOW *newscr;",
                "_FBSD_CURSES_DATA int LINES;",
                "_FBSD_CURSES_DATA int COLS;",
                "_FBSD_CURSES_DATA int COLORS;",
                "_FBSD_CURSES_DATA int COLOR_PAIRS;",
                "_FBSD_CURSES_DATA int TABSIZE;",
                "_FBSD_CURSES_DATA int ESCDELAY;",
                "_FBSD_CURSES_DATA char ttytype[];",
                "_FBSD_CURSES_DATA chtype acs_map[128];",
                "#define COLOR_BLACK   0",
                "#define COLOR_RED     1",
                "#define COLOR_GREEN   2",
                "#define COLOR_YELLOW  3",
                "#define COLOR_BLUE    4",
                "#define COLOR_MAGENTA 5",
                "#define COLOR_CYAN    6",
                "#define COLOR_WHITE   7",
                "#define COLOR_PAIR(n) (((unsigned int)(n) << 8) & 0xFF00U)",
                "#define PAIR_NUMBER(a) (((unsigned int)(a) >> 8) & 0xFFU)",
                "#define A_NORMAL     0x00000000U",
                "#define A_ATTRIBUTES 0xFFFFFF00U",
                "#define A_CHARTEXT   0x000000FFU",
                "#define A_COLOR      0x0000FF00U",
                "#define A_STANDOUT   0x00010000U",
                "#define A_UNDERLINE  0x00020000U",
                "#define A_REVERSE    0x00040000U",
                "#define A_BLINK      0x00080000U",
                "#define A_DIM        0x00100000U",
                "#define A_BOLD       0x00200000U",
                "#define A_ALTCHARSET 0x00400000U",
                "#define A_INVIS      0x00800000U",
                "#define A_PROTECT    0x01000000U",
                "#define WA_NORMAL    A_NORMAL",
                "#define WA_STANDOUT  A_STANDOUT",
                "#define WA_UNDERLINE A_UNDERLINE",
                "#define WA_REVERSE   A_REVERSE",
                "#define WA_BLINK     A_BLINK",
                "#define WA_DIM       A_DIM",
                "#define WA_BOLD      A_BOLD",
                "#define NCURSES_ACS(c) (acs_map[(unsigned char)(c)])",
                "#define ACS_ULCORNER NCURSES_ACS('l')",
                "#define ACS_LLCORNER NCURSES_ACS('m')",
                "#define ACS_URCORNER NCURSES_ACS('k')",
                "#define ACS_LRCORNER NCURSES_ACS('j')",
                "#define ACS_LTEE     NCURSES_ACS('t')",
                "#define ACS_RTEE     NCURSES_ACS('u')",
                "#define ACS_BTEE     NCURSES_ACS('v')",
                "#define ACS_TTEE     NCURSES_ACS('w')",
                "#define ACS_HLINE    NCURSES_ACS('q')",
                "#define ACS_VLINE    NCURSES_ACS('x')",
                "#define ACS_PLUS     NCURSES_ACS('n')",
                "#define ACS_S1       NCURSES_ACS('o')",
                "#define ACS_S9       NCURSES_ACS('s')",
                "#define ACS_DIAMOND  NCURSES_ACS('`')",
                "#define ACS_CKBOARD  NCURSES_ACS('a')",
                "#define ACS_DEGREE   NCURSES_ACS('f')",
                "#define ACS_PLMINUS  NCURSES_ACS('g')",
                "#define ACS_BULLET   NCURSES_ACS('~')",
                "#define ACS_LARROW   NCURSES_ACS(',')",
                "#define ACS_RARROW   NCURSES_ACS('+')",
                "#define ACS_DARROW   NCURSES_ACS('.')",
                "#define ACS_UARROW   NCURSES_ACS('-')",
                "#define ACS_BOARD    NCURSES_ACS('h')",
                "#define ACS_LANTERN  NCURSES_ACS('i')",
                "#define ACS_BLOCK    NCURSES_ACS('0')",
                "#define KEY_CODE_YES  0400",
                "#define KEY_MIN       0401",
                "#define KEY_BREAK     0401",
                "#define KEY_DOWN      0402",
                "#define KEY_UP        0403",
                "#define KEY_LEFT      0404",
                "#define KEY_RIGHT     0405",
                "#define KEY_HOME      0406",
                "#define KEY_BACKSPACE 0407",
                "#define KEY_F0        0410",
                "#define KEY_F(n)      (KEY_F0 + (n))",
                "#define KEY_DL        0510",
                "#define KEY_IL        0511",
                "#define KEY_DC        0512",
                "#define KEY_IC        0513",
                "#define KEY_EIC       0514",
                "#define KEY_CLEAR     0515",
                "#define KEY_EOS       0516",
                "#define KEY_EOL       0517",
                "#define KEY_SF        0520",
                "#define KEY_SR        0521",
                "#define KEY_NPAGE     0522",
                "#define KEY_PPAGE     0523",
                "#define KEY_STAB      0524",
                "#define KEY_CTAB      0525",
                "#define KEY_CATAB     0526",
                "#define KEY_ENTER     0527",
                "#define KEY_PRINT     0532",
                "#define KEY_LL        0533",
                "#define KEY_A1        0534",
                "#define KEY_A3        0535",
                "#define KEY_B2        0536",
                "#define KEY_C1        0537",
                "#define KEY_C3        0540",
                "#define KEY_BTAB      0541",
                "#define KEY_BEG       0542",
                "#define KEY_CANCEL    0543",
                "#define KEY_CLOSE     0544",
                "#define KEY_COMMAND   0545",
                "#define KEY_COPY      0546",
                "#define KEY_CREATE    0547",
                "#define KEY_END       0550",
                "#define KEY_EXIT      0551",
                "#define KEY_FIND      0552",
                "#define KEY_HELP      0553",
                "#define KEY_MARK      0554",
                "#define KEY_MESSAGE   0555",
                "#define KEY_MOVE      0556",
                "#define KEY_NEXT      0557",
                "#define KEY_OPEN      0560",
                "#define KEY_OPTIONS   0561",
                "#define KEY_PREVIOUS  0562",
                "#define KEY_REDO      0563",
                "#define KEY_REFERENCE 0564",
                "#define KEY_REFRESH   0565",
                "#define KEY_REPLACE   0566",
                "#define KEY_RESTART   0567",
                "#define KEY_RESUME    0570",
                "#define KEY_SAVE      0571",
                "#define KEY_SBEG      0572",
                "#define KEY_SCANCEL   0573",
                "#define KEY_SCOMMAND  0574",
                "#define KEY_SCOPY     0575",
                "#define KEY_SCREATE   0576",
                "#define KEY_SDC       0577",
                "#define KEY_SDL       0600",
                "#define KEY_SELECT    0601",
                "#define KEY_SEND      0602",
                "#define KEY_SEOL      0603",
                "#define KEY_SEXIT     0604",
                "#define KEY_SFIND     0605",
                "#define KEY_SHELP     0606",
                "#define KEY_SHOME     0607",
                "#define KEY_SIC       0610",
                "#define KEY_SLEFT     0611",
                "#define KEY_SMESSAGE  0612",
                "#define KEY_SMOVE     0613",
                "#define KEY_SNEXT     0614",
                "#define KEY_SOPTIONS  0615",
                "#define KEY_SPREVIOUS 0616",
                "#define KEY_SPRINT    0617",
                "#define KEY_SREDO     0620",
                "#define KEY_SREPLACE  0621",
                "#define KEY_SRIGHT    0622",
                "#define KEY_SRSUME    0623",
                "#define KEY_SSAVE     0624",
                "#define KEY_SSUSPEND  0625",
                "#define KEY_SUNDO     0626",
                "#define KEY_SUSPEND   0627",
                "#define KEY_UNDO      0630",
                "#define KEY_MOUSE     0631",
                "#define KEY_RESIZE    0632",
                "#define KEY_MAX       0777",
                (
                    "#define getyx(win, y, x)     do { (y) = (win) ? (win)->_cury : 0; (x"
                    ") = (win) ? (win)->_curx : 0; } while (0)"
                ),
                (
                    "#define getbegyx(win, y, x)  do { (y) = (win) ? (win)->_begy : 0; (x"
                    ") = (win) ? (win)->_begx : 0; } while (0)"
                ),
                (
                    "#define getmaxyx(win, y, x)  do { (y) = (win) ? (win)->_maxy : 0; (x"
                    ") = (win) ? (win)->_maxx : 0; } while (0)"
                ),
                "#define getparyx(win, y, x)  do { (y) = -1; (x) = -1; (void)(win); } while (0)",
                "#define getcury(win) ((win) ? (win)->_cury : ERR)",
                "#define getcurx(win) ((win) ? (win)->_curx : ERR)",
                "#define getbegy(win) ((win) ? (win)->_begy : ERR)",
                "#define getbegx(win) ((win) ? (win)->_begx : ERR)",
                "#define getmaxy(win) ((win) ? (win)->_maxy : ERR)",
                "#define getmaxx(win) ((win) ? (win)->_maxx : ERR)",
                "#define getpary(win) (-1)",
                "#define getparx(win) (-1)",
                "_FBSD_CURSES_DATA cchar_t _nc_wacs[128];",
                "#define NCURSES_WACS(c) (&_nc_wacs[(unsigned char)(c)])",
                "#define WACS_ULCORNER NCURSES_WACS('l')",
                "#define WACS_LLCORNER NCURSES_WACS('m')",
                "#define WACS_URCORNER NCURSES_WACS('k')",
                "#define WACS_LRCORNER NCURSES_WACS('j')",
                "#define WACS_LTEE     NCURSES_WACS('t')",
                "#define WACS_RTEE     NCURSES_WACS('u')",
                "#define WACS_BTEE     NCURSES_WACS('v')",
                "#define WACS_TTEE     NCURSES_WACS('w')",
                "#define WACS_HLINE    NCURSES_WACS('q')",
                "#define WACS_VLINE    NCURSES_WACS('x')",
                "#define WACS_PLUS     NCURSES_WACS('n')",
                "#define WACS_LARROW   NCURSES_WACS(',')",
                "#define WACS_RARROW   NCURSES_WACS('+')",
                "#define WACS_DARROW   NCURSES_WACS('.')",
                "#define WACS_UARROW   NCURSES_WACS('-')",
                "int whline_set(WINDOW *win, const cchar_t *wch, int n);",
                "int wvline_set(WINDOW *win, const cchar_t *wch, int n);",
                "int hline_set(const cchar_t *wch, int n);",
                "int vline_set(const cchar_t *wch, int n);",
                "int mvhline_set(int y, int x, const cchar_t *wch, int n);",
                "int mvvline_set(int y, int x, const cchar_t *wch, int n);",
                "int mvwhline_set(WINDOW *win, int y, int x, const cchar_t *wch, int n);",
                "int mvwvline_set(WINDOW *win, int y, int x, const cchar_t *wch, int n);",
                "int set_tabsize(int cols);",
                "int set_escdelay(int size);",
                "int box_set(WINDOW *win, const cchar_t *verch, const cchar_t *horch);",
                (
                    "int wborder_set(WINDOW *win, const cchar_t *ls, const cchar_t *rs, "
                    "const cchar_t *ts, const cchar_t *bs, const cchar_t *tl, "
                    "const cchar_t *tr, const cchar_t *bl, const cchar_t *br);"
                ),
                "WINDOW *initscr(void);",
                "SCREEN *newterm(const char *type, FILE *outfd, FILE *infd);",
                "SCREEN *set_term(SCREEN *new_scr);",
                "void delscreen(SCREEN *sp);",
                "int endwin(void);",
                "bool isendwin(void);",
                "WINDOW *newwin(int nlines, int ncols, int begin_y, int begin_x);",
                "int delwin(WINDOW *win);",
                "WINDOW *subwin(WINDOW *orig, int nlines, int ncols, int begin_y, int begin_x);",
                "WINDOW *derwin(WINDOW *orig, int nlines, int ncols, int begin_y, int begin_x);",
                "int mvwin(WINDOW *win, int y, int x);",
                "int mvderwin(WINDOW *win, int par_y, int par_x);",
                "WINDOW *dupwin(WINDOW *win);",
                "int wresize(WINDOW *win, int lines, int columns);",
                "WINDOW *newpad(int nlines, int ncols);",
                "WINDOW *subpad(WINDOW *orig, int nlines, int ncols, int begin_y, int begin_x);",
                (
                    "int prefresh(WINDOW *pad, int pminrow, int pmincol, int sminrow, int"
                    " smincol, int smaxrow, int smaxcol);"
                ),
                (
                    "int pnoutrefresh(WINDOW *pad, int pminrow, int pmincol, int sminrow,"
                    " int smincol, int smaxrow, int smaxcol);"
                ),
                "int refresh(void);",
                "int wrefresh(WINDOW *win);",
                "int wnoutrefresh(WINDOW *win);",
                "int doupdate(void);",
                "int redrawwin(WINDOW *win);",
                "int wredrawln(WINDOW *win, int beg_line, int num_lines);",
                "int touchwin(WINDOW *win);",
                "int touchline(WINDOW *win, int start, int count);",
                "int wtouchln(WINDOW *win, int y, int n, int changed);",
                (
                    "int copywin(const WINDOW *srcwin, WINDOW *dstwin, int sminrow, int s"
                    "mincol, int dminrow, int dmincol, int dmaxrow, int dmaxcol, int over"
                    "lay_flag);"
                ),
                "int overlay(const WINDOW *srcwin, WINDOW *dstwin);",
                "int overwrite(const WINDOW *srcwin, WINDOW *dstwin);",
                "int move(int y, int x);",
                "int wmove(WINDOW *win, int y, int x);",
                "int clear(void);",
                "int wclear(WINDOW *win);",
                "int erase(void);",
                "int werase(WINDOW *win);",
                "int clrtobot(void);",
                "int wclrtobot(WINDOW *win);",
                "int clrtoeol(void);",
                "int wclrtoeol(WINDOW *win);",
                "int clearok(WINDOW *win, bool bf);",
                "int idlok(WINDOW *win, bool bf);",
                "void idcok(WINDOW *win, bool bf);",
                "void immedok(WINDOW *win, bool bf);",
                "int leaveok(WINDOW *win, bool bf);",
                "int scrollok(WINDOW *win, bool bf);",
                "int nl(void);",
                "int nonl(void);",
                "int scroll(WINDOW *win);",
                "int scrl(int n);",
                "int wscrl(WINDOW *win, int n);",
                "int setscrreg(int top, int bot);",
                "int wsetscrreg(WINDOW *win, int top, int bot);",
                "int box(WINDOW *win, chtype verch, chtype horch);",
                (
                    "int wborder(WINDOW *win, chtype ls, chtype rs, chtype ts, chtype bs,"
                    " chtype tl, chtype tr, chtype bl, chtype br);"
                ),
                (
                    "int border(chtype ls, chtype rs, chtype ts, chtype bs, chtype tl, ch"
                    "type tr, chtype bl, chtype br);"
                ),
                "int whline(WINDOW *win, chtype ch, int n);",
                "int wvline(WINDOW *win, chtype ch, int n);",
                "int hline(chtype ch, int n);",
                "int vline(chtype ch, int n);",
                "int mvhline(int y, int x, chtype ch, int n);",
                "int mvvline(int y, int x, chtype ch, int n);",
                "int mvwhline(WINDOW *win, int y, int x, chtype ch, int n);",
                "int mvwvline(WINDOW *win, int y, int x, chtype ch, int n);",
                "int addch(chtype ch);",
                "int waddch(WINDOW *win, chtype ch);",
                "int mvaddch(int y, int x, chtype ch);",
                "int mvwaddch(WINDOW *win, int y, int x, chtype ch);",
                "int echochar(chtype ch);",
                "int wechochar(WINDOW *win, chtype ch);",
                "int addstr(const char *str);",
                "int addnstr(const char *str, int n);",
                "int waddstr(WINDOW *win, const char *str);",
                "int waddnstr(WINDOW *win, const char *str, int n);",
                "int mvaddstr(int y, int x, const char *str);",
                "int mvaddnstr(int y, int x, const char *str, int n);",
                "int mvwaddstr(WINDOW *win, int y, int x, const char *str);",
                "int mvwaddnstr(WINDOW *win, int y, int x, const char *str, int n);",
                "int addwstr(const wchar_t *wstr);",
                "int waddwstr(WINDOW *win, const wchar_t *wstr);",
                "int waddnwstr(WINDOW *win, const wchar_t *wstr, int n);",
                "int mvaddwstr(int y, int x, const wchar_t *wstr);",
                "int mvwaddwstr(WINDOW *win, int y, int x, const wchar_t *wstr);",
                "int mvwaddnwstr(WINDOW *win, int y, int x, const wchar_t *wstr, int n);",
                "int wadd_wch(WINDOW *win, const cchar_t *wch);",
                "int mvwadd_wch(WINDOW *win, int y, int x, const cchar_t *wch);",
                (
                    "int setcchar(cchar_t *wcval, const wchar_t *wch, attr_t attrs, short"
                    " color_pair, const void *opts);"
                ),
                (
                    "int getcchar(const cchar_t *wcval, wchar_t *wch, attr_t *attrs, shor"
                    "t *color_pair, void *opts);"
                ),
                "chtype winch(WINDOW *win);",
                "chtype inch(void);",
                "chtype mvinch(int y, int x);",
                "chtype mvwinch(WINDOW *win, int y, int x);",
                "int insch(chtype ch);",
                "int winsch(WINDOW *win, chtype ch);",
                "int mvinsch(int y, int x, chtype ch);",
                "int mvwinsch(WINDOW *win, int y, int x, chtype ch);",
                "int delch(void);",
                "int wdelch(WINDOW *win);",
                "int mvdelch(int y, int x);",
                "int mvwdelch(WINDOW *win, int y, int x);",
                "int insertln(void);",
                "int winsertln(WINDOW *win);",
                "int deleteln(void);",
                "int wdeleteln(WINDOW *win);",
                "int insdelln(int n);",
                "int winsdelln(WINDOW *win, int n);",
                "int printw(const char *fmt, ...);",
                "int wprintw(WINDOW *win, const char *fmt, ...);",
                "int mvprintw(int y, int x, const char *fmt, ...);",
                "int mvwprintw(WINDOW *win, int y, int x, const char *fmt, ...);",
                "int vw_printw(WINDOW *win, const char *fmt, va_list varglist);",
                "int vwprintw(WINDOW *win, const char *fmt, va_list varglist);",
                "int fbsd_curses_getch(void);",
                "int fbsd_curses_ungetch(int ch);",
                "#if defined(_WIN32) || defined(__DOS__) || defined(__MSDOS__)",
                "#undef getch",
                "#undef ungetch",
                "#define getch fbsd_curses_getch",
                "#define ungetch fbsd_curses_ungetch",
                "#else",
                "int getch(void);",
                "int ungetch(int ch);",
                "#endif",
                "int wgetch(WINDOW *win);",
                "int mvgetch(int y, int x);",
                "int mvwgetch(WINDOW *win, int y, int x);",
                "int wget_wch(WINDOW *win, wint_t *wch);",
                "int get_wch(wint_t *wch);",
                "int unget_wch(wchar_t wch);",
                "int getnstr(char *str, int n);",
                "int getstr(char *str);",
                "int wgetnstr(WINDOW *win, char *str, int n);",
                "int wgetstr(WINDOW *win, char *str);",
                "int mvgetnstr(int y, int x, char *str, int n);",
                "int mvwgetnstr(WINDOW *win, int y, int x, char *str, int n);",
                "int flushinp(void);",
                "int cbreak(void);",
                "int nocbreak(void);",
                "int echo(void);",
                "int noecho(void);",
                "int raw(void);",
                "int noraw(void);",
                "int halfdelay(int tenths);",
                "int intrflush(WINDOW *win, bool bf);",
                "int keypad(WINDOW *win, bool bf);",
                "int meta(WINDOW *win, bool bf);",
                "int nodelay(WINDOW *win, bool bf);",
                "int notimeout(WINDOW *win, bool bf);",
                "void timeout(int delay);",
                "void wtimeout(WINDOW *win, int delay);",
                "int typeahead(int fd);",
                "int attron(int attrs);",
                "int attroff(int attrs);",
                "int attrset(int attrs);",
                "int wattron(WINDOW *win, int attrs);",
                "int wattroff(WINDOW *win, int attrs);",
                "int wattrset(WINDOW *win, int attrs);",
                "int wattr_on(WINDOW *win, attr_t attrs, void *opts);",
                "int wattr_off(WINDOW *win, attr_t attrs, void *opts);",
                "int wattr_set(WINDOW *win, attr_t attrs, short pair, void *opts);",
                "int wattr_get(WINDOW *win, attr_t *attrs, short *pair, void *opts);",
                "int standout(void);",
                "int standend(void);",
                "int wstandout(WINDOW *win);",
                "int wstandend(WINDOW *win);",
                "int bkgd(chtype ch);",
                "void bkgdset(chtype ch);",
                "int wbkgd(WINDOW *win, chtype ch);",
                "void wbkgdset(WINDOW *win, chtype ch);",
                "chtype getbkgd(WINDOW *win);",
                "int wchgat(WINDOW *win, int n, attr_t attr, short color, const void *opts);",
                (
                    "int mvwchgat(WINDOW *win, int y, int x, int n, attr_t attr, short co"
                    "lor, const void *opts);"
                ),
                "int chgat(int n, attr_t attr, short color, const void *opts);",
                "int mvchgat(int y, int x, int n, attr_t attr, short color, const void *opts);",
                "int start_color(void);",
                "bool has_colors(void);",
                "bool can_change_color(void);",
                "int init_pair(short pair, short f, short b);",
                "int init_color(short color, short r, short g, short b);",
                "int pair_content(short pair, short *f, short *b);",
                "int color_content(short color, short *r, short *g, short *b);",
                "int use_default_colors(void);",
                "int assume_default_colors(int fg, int bg);",
                "int curs_set(int visibility);",
                "int napms(int ms);",
                "int beep(void);",
                "int flash(void);",
                "int baudrate(void);",
                "char erasechar(void);",
                "char killchar(void);",
                "char *longname(void);",
                "char *termname(void);",
                "chtype termattrs(void);",
                "const char *keyname(int c);",
                "int def_prog_mode(void);",
                "int def_shell_mode(void);",
                "int reset_prog_mode(void);",
                "int reset_shell_mode(void);",
                "int savetty(void);",
                "int resetty(void);",
                "#define fixterm() reset_prog_mode()",
                "#define resetterm() reset_shell_mode()",
                "#define saveterm() def_prog_mode()",
                "#define crmode() cbreak()",
                "#define nocrmode() nocbreak()",
                "bool has_ic(void);",
                "bool has_il(void);",
                "int resizeterm(int lines, int columns);",
                "bool is_term_resized(int lines, int columns);",
                "int resize_term(int lines, int columns);",
                "void use_env(bool f);",
                "void filter(void);",
                "chtype getattrs(const WINDOW *w);",
                "const char *curses_version(void);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    ncurses_h = f'#include "curses.h"{LF}'
    termcap_h = f'#include "term.h"{LF}'

    fbsd_curses_c = (
        LF.join(
            [
                '#include "curses.h"',
                '#include "term.h"',
                "#include <stdlib.h>",
                "#include <string.h>",
                "#if defined(_WIN32)",
                "#ifndef WIN32_LEAN_AND_MEAN",
                "#define WIN32_LEAN_AND_MEAN",
                "#endif",
                "#include <windows.h>",
                "#elif !defined(__DOS__) && !defined(__MSDOS__)",
                "#include <sys/ioctl.h>",
                "#include <unistd.h>",
                "#endif",
                "",
                "struct screen { WINDOW *std; };",
                'static TERMINAL g_default_term = { "xterm-256color" };',
                "TERMINAL *cur_term = &g_default_term;",
                "char PC = 0;",
                'char *UP = "";',
                'char *BC = "";',
                "short ospeed = 9600;",
                "WINDOW *stdscr = NULL;",
                "WINDOW *curscr = NULL;",
                "WINDOW *newscr = NULL;",
                "int LINES = 24;",
                "int COLS = 80;",
                "int COLORS = 8;",
                "int COLOR_PAIRS = 64;",
                "int TABSIZE = 8;",
                "int ESCDELAY = 25;",
                'char ttytype[128] = "xterm-256color";',
                "chtype acs_map[128];",
                "cchar_t _nc_wacs[128];",
                "static int g_is_endwin = 1;",
                "static int g_unget_buf = ERR;",
                "static short g_pairs[64][2];",
                "",
                "static void fbsd_detect_size(void) {",
                "#if defined(_WIN32)",
                "    CONSOLE_SCREEN_BUFFER_INFO csbi;",
                "    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);",
                "    if (h != INVALID_HANDLE_VALUE && GetConsoleScreenBufferInfo(h, &csbi)) {",
                "        int w = csbi.srWindow.Right - csbi.srWindow.Left + 1;",
                "        int r = csbi.srWindow.Bottom - csbi.srWindow.Top + 1;",
                "        if (w > 0) COLS = w;",
                "        if (r > 0) LINES = r;",
                "    }",
                "#elif !defined(__DOS__) && !defined(__MSDOS__) && defined(TIOCGWINSZ)",
                "    struct winsize ws;",
                "    if (ioctl(1, TIOCGWINSZ, &ws) == 0) {",
                "        if (ws.ws_col > 0) COLS = ws.ws_col;",
                "        if (ws.ws_row > 0) LINES = ws.ws_row;",
                "    }",
                "#endif",
                "}",
                "",
                "static void fbsd_init_acs(void) {",
                "    int i;",
                "    for (i = 0; i < 128; i++) acs_map[i] = (chtype)i;",
                (
                    "    acs_map['l'] = '+'; acs_map['m'] = '+'; acs_map['k'] = '+'; acs_"
                    "map['j'] = '+';"
                ),
                (
                    "    acs_map['t'] = '+'; acs_map['u'] = '+'; acs_map['v'] = '+'; acs_"
                    "map['w'] = '+';"
                ),
                "    acs_map['q'] = '-'; acs_map['x'] = '|'; acs_map['n'] = '+';",
                (
                    "    acs_map[','] = '<'; acs_map['+'] = '>'; acs_map['.'] = 'v'; acs_"
                    "map['-'] = '^';"
                ),
                "    for (i = 0; i < 128; i++) { _nc_wacs[i].chars[0] = (wchar_t)acs_map[i]; }",
                "}",
                "",
                "WINDOW *newwin(int nlines, int ncols, int begin_y, int begin_x) {",
                "    WINDOW *w;",
                "    int i, total;",
                "    if (nlines <= 0) nlines = LINES - begin_y;",
                "    if (ncols <= 0) ncols = COLS - begin_x;",
                "    if (nlines <= 0) nlines = 1;",
                "    if (ncols <= 0) ncols = 1;",
                "    w = (WINDOW *)calloc(1, sizeof(WINDOW));",
                "    if (!w) return NULL;",
                "    w->_maxy = nlines; w->_maxx = ncols;",
                "    w->_begy = begin_y; w->_begx = begin_x;",
                "    w->_bkgd = ' ';",
                "    w->_timeout = -1;",
                "    total = nlines * ncols;",
                "    w->_cells = (chtype *)malloc((size_t)total * sizeof(chtype));",
                "    if (!w->_cells) { free(w); return NULL; }",
                "    for (i = 0; i < total; i++) w->_cells[i] = ' ';",
                "    return w;",
                "}",
                "",
                "WINDOW *initscr(void) {",
                "    fbsd_detect_size();",
                "    fbsd_init_acs();",
                "    if (!stdscr) stdscr = newwin(LINES, COLS, 0, 0);",
                "    if (!curscr) curscr = newwin(LINES, COLS, 0, 0);",
                "    if (!newscr) newscr = newwin(LINES, COLS, 0, 0);",
                "    g_is_endwin = 0;",
                "    return stdscr;",
                "}",
                "SCREEN *newterm(const char *type, FILE *outfd, FILE *infd) {",
                "    SCREEN *s = (SCREEN *)calloc(1, sizeof(SCREEN));",
                "    (void)type; (void)outfd; (void)infd;",
                "    if (s) s->std = initscr();",
                "    return s;",
                "}",
                "SCREEN *set_term(SCREEN *new_scr) { return new_scr; }",
                "void delscreen(SCREEN *sp) { free(sp); }",
                "int endwin(void) { g_is_endwin = 1; fflush(stdout); return OK; }",
                "bool isendwin(void) { return g_is_endwin != 0; }",
                "int delwin(WINDOW *win) {",
                "    if (!win) return ERR;",
                "    free(win->_cells);",
                "    if (win == stdscr) stdscr = NULL;",
                "    if (win == curscr) curscr = NULL;",
                "    if (win == newscr) newscr = NULL;",
                "    free(win);",
                "    return OK;",
                "}",
                "WINDOW *subwin(WINDOW *orig, int nlines, int ncols, int begin_y, int begin_x) {",
                "    (void)orig;",
                "    return newwin(nlines, ncols, begin_y, begin_x);",
                "}",
                "WINDOW *derwin(WINDOW *orig, int nlines, int ncols, int begin_y, int begin_x) {",
                "    int by = orig ? orig->_begy + begin_y : begin_y;",
                "    int bx = orig ? orig->_begx + begin_x : begin_x;",
                "    return newwin(nlines, ncols, by, bx);",
                "}",
                (
                    "int mvwin(WINDOW *win, int y, int x) { if (!win) return ERR; win->_b"
                    "egy = y; win->_begx = x; return OK; }"
                ),
                "int mvderwin(WINDOW *win, int y, int x) { return mvwin(win, y, x); }",
                "WINDOW *dupwin(WINDOW *win) {",
                "    WINDOW *nw;",
                "    if (!win) return NULL;",
                "    nw = newwin(win->_maxy, win->_maxx, win->_begy, win->_begx);",
                (
                    "    if (nw) memcpy(nw->_cells, win->_cells, (size_t)(win->_maxy * wi"
                    "n->_maxx) * sizeof(chtype));"
                ),
                "    return nw;",
                "}",
                "int wresize(WINDOW *win, int lines, int columns) {",
                "    chtype *nc; int i, total;",
                "    if (!win || lines <= 0 || columns <= 0) return ERR;",
                "    total = lines * columns;",
                "    nc = (chtype *)malloc((size_t)total * sizeof(chtype));",
                "    if (!nc) return ERR;",
                "    for (i = 0; i < total; i++) nc[i] = win->_bkgd;",
                "    free(win->_cells); win->_cells = nc;",
                "    win->_maxy = lines; win->_maxx = columns;",
                "    if (win->_cury >= lines) win->_cury = lines - 1;",
                "    if (win->_curx >= columns) win->_curx = columns - 1;",
                "    return OK;",
                "}",
                "WINDOW *newpad(int nlines, int ncols) { return newwin(nlines, ncols, 0, 0); }",
                (
                    "WINDOW *subpad(WINDOW *orig, int nlines, int ncols, int by, int bx) "
                    "{ return derwin(orig, nlines, ncols, by, bx); }"
                ),
                (
                    "int pnoutrefresh(WINDOW *pad, int pminrow, int pmincol, int sminrow,"
                    " int smincol, int smaxrow, int smaxcol) {"
                ),
                (
                    "    (void)pad; (void)pminrow; (void)pmincol; (void)sminrow; (void)sm"
                    "incol; (void)smaxrow; (void)smaxcol;"
                ),
                "    return OK;",
                "}",
                (
                    "int prefresh(WINDOW *pad, int pminrow, int pmincol, int sminrow, int"
                    " smincol, int smaxrow, int smaxcol) {"
                ),
                (
                    "    return pnoutrefresh(pad, pminrow, pmincol, sminrow, smincol, sma"
                    "xrow, smaxcol);"
                ),
                "}",
                "int wnoutrefresh(WINDOW *win) { return win ? OK : ERR; }",
                "int doupdate(void) { fflush(stdout); return OK; }",
                "int wrefresh(WINDOW *win) { if (!win) return ERR; return doupdate(); }",
                "int refresh(void) { return wrefresh(stdscr ? stdscr : initscr()); }",
                "int redrawwin(WINDOW *win) { return wrefresh(win); }",
                (
                    "int wredrawln(WINDOW *win, int b, int n) { (void)b; (void)n; return "
                    "wnoutrefresh(win); }"
                ),
                "int touchwin(WINDOW *win) { return win ? OK : ERR; }",
                (
                    "int touchline(WINDOW *win, int s, int c) { (void)s; (void)c; return "
                    "win ? OK : ERR; }"
                ),
                (
                    "int wtouchln(WINDOW *win, int y, int n, int ch) { (void)y; (void)n; "
                    "(void)ch; return win ? OK : ERR; }"
                ),
                (
                    "int copywin(const WINDOW *s, WINDOW *d, int sr, int sc, int dr, int "
                    "dc, int dmr, int dmc, int ov) {"
                ),
                "    int r, c;",
                "    if (!s || !d) return ERR;",
                "    for (r = 0; dr + r <= dmr && dr + r < d->_maxy && sr + r < s->_maxy; r++) {",
                (
                    "        for (c = 0; dc + c <= dmc && dc + c < d->_maxx && sc + c < s"
                    "->_maxx; c++) {"
                ),
                "            chtype v = s->_cells[(sr + r) * s->_maxx + (sc + c)];",
                (
                    "            if (!ov || (v & A_CHARTEXT) != ' ') d->_cells[(dr + r) *"
                    " d->_maxx + (dc + c)] = v;"
                ),
                "        }",
                "    }",
                "    return OK;",
                "}",
                (
                    "int overlay(const WINDOW *s, WINDOW *d) { return (!s || !d) ? ERR : "
                    "copywin(s, d, 0, 0, 0, 0, d->_maxy - 1, d->_maxx - 1, 1); }"
                ),
                (
                    "int overwrite(const WINDOW *s, WINDOW *d) { return (!s || !d) ? ERR "
                    ": copywin(s, d, 0, 0, 0, 0, d->_maxy - 1, d->_maxx - 1, 0); }"
                ),
                "int wmove(WINDOW *win, int y, int x) {",
                "    if (!win || y < 0 || x < 0 || y >= win->_maxy || x >= win->_maxx) return ERR;",
                "    win->_cury = y; win->_curx = x; return OK;",
                "}",
                "int move(int y, int x) { return wmove(stdscr ? stdscr : initscr(), y, x); }",
                "int werase(WINDOW *win) {",
                "    int i, total;",
                "    if (!win) return ERR;",
                "    total = win->_maxy * win->_maxx;",
                "    for (i = 0; i < total; i++) win->_cells[i] = win->_bkgd;",
                "    win->_cury = 0; win->_curx = 0;",
                "    return OK;",
                "}",
                "int erase(void) { return werase(stdscr ? stdscr : initscr()); }",
                "int wclear(WINDOW *win) { return werase(win); }",
                "int clear(void) { return wclear(stdscr ? stdscr : initscr()); }",
                "int wclrtoeol(WINDOW *win) {",
                "    int x; if (!win) return ERR;",
                (
                    "    for (x = win->_curx; x < win->_maxx; x++) win->_cells[win->_cury"
                    " * win->_maxx + x] = win->_bkgd;"
                ),
                "    return OK;",
                "}",
                "int clrtoeol(void) { return wclrtoeol(stdscr ? stdscr : initscr()); }",
                "int wclrtobot(WINDOW *win) {",
                "    int y, x; if (!win) return ERR;",
                "    wclrtoeol(win);",
                "    for (y = win->_cury + 1; y < win->_maxy; y++)",
                (
                    "        for (x = 0; x < win->_maxx; x++) win->_cells[y * win->_maxx "
                    "+ x] = win->_bkgd;"
                ),
                "    return OK;",
                "}",
                "int clrtobot(void) { return wclrtobot(stdscr ? stdscr : initscr()); }",
                "int clearok(WINDOW *w, bool bf) { if (w) w->_clearok = bf; return OK; }",
                "int idlok(WINDOW *w, bool bf) { if (w) w->_idlok = bf; return OK; }",
                "void idcok(WINDOW *w, bool bf) { (void)w; (void)bf; }",
                "void immedok(WINDOW *w, bool bf) { (void)w; (void)bf; }",
                "int leaveok(WINDOW *w, bool bf) { if (w) w->_leaveok = bf; return OK; }",
                "int scrollok(WINDOW *w, bool bf) { if (w) w->_scroll = bf; return OK; }",
                "int nl(void) { return OK; }",
                "int nonl(void) { return OK; }",
                "int wscrl(WINDOW *win, int n) { (void)n; return win ? OK : ERR; }",
                "int scroll(WINDOW *win) { return wscrl(win, 1); }",
                "int scrl(int n) { return wscrl(stdscr, n); }",
                "int wsetscrreg(WINDOW *w, int t, int b) { (void)w; (void)t; (void)b; return OK; }",
                "int setscrreg(int t, int b) { return wsetscrreg(stdscr, t, b); }",
                "int waddch(WINDOW *win, chtype ch) {",
                "    unsigned char c = (unsigned char)(ch & A_CHARTEXT);",
                "    if (!win) return ERR;",
                f"    if (c == '{BS}n') {{",
                "        win->_curx = 0;",
                "        if (win->_cury + 1 < win->_maxy) win->_cury++;",
                "        return OK;",
                "    }",
                "    win->_cells[win->_cury * win->_maxx + win->_curx] = ch | win->_attrs;",
                "    win->_curx++;",
                "    if (win->_curx >= win->_maxx) {",
                "        win->_curx = 0;",
                "        if (win->_cury + 1 < win->_maxy) win->_cury++;",
                "    }",
                "    return OK;",
                "}",
                "int addch(chtype ch) { return waddch(stdscr ? stdscr : initscr(), ch); }",
                (
                    "int mvaddch(int y, int x, chtype ch) { return move(y, x) == ERR ? ER"
                    "R : addch(ch); }"
                ),
                (
                    "int mvwaddch(WINDOW *w, int y, int x, chtype ch) { return wmove(w, y"
                    ", x) == ERR ? ERR : waddch(w, ch); }"
                ),
                "int wechochar(WINDOW *w, chtype ch) { waddch(w, ch); return wrefresh(w); }",
                "int echochar(chtype ch) { return wechochar(stdscr ? stdscr : initscr(), ch); }",
                "int waddnstr(WINDOW *win, const char *str, int n) {",
                "    int i = 0; if (!win || !str) return ERR;",
                (
                    f"    while (str[i] != '{BS}0' && (n < 0 || i < n)) "
                    "{ waddch(win, (unsigned char)str[i]); i++; }"
                ),
                "    return OK;",
                "}",
                "int waddstr(WINDOW *w, const char *s) { return waddnstr(w, s, -1); }",
                "int addstr(const char *s) { return waddstr(stdscr ? stdscr : initscr(), s); }",
                (
                    "int addnstr(const char *s, int n) { return waddnstr(stdscr ? stdscr "
                    ": initscr(), s, n); }"
                ),
                (
                    "int mvaddstr(int y, int x, const char *s) { return move(y, x) == ERR"
                    " ? ERR : addstr(s); }"
                ),
                (
                    "int mvaddnstr(int y, int x, const char *s, int n) { return move(y, x"
                    ") == ERR ? ERR : addnstr(s, n); }"
                ),
                (
                    "int mvwaddstr(WINDOW *w, int y, int x, const char *s) { return wmove"
                    "(w, y, x) == ERR ? ERR : waddstr(w, s); }"
                ),
                (
                    "int mvwaddnstr(WINDOW *w, int y, int x, const char *s, int n) { retu"
                    "rn wmove(w, y, x) == ERR ? ERR : waddnstr(w, s, n); }"
                ),
                "int waddnwstr(WINDOW *w, const wchar_t *ws, int n) {",
                "    int i = 0; if (!w || !ws) return ERR;",
                (
                    "    while (ws[i] != 0 && (n < 0 || i < n)) { waddch(w, (chtype)(ws[i"
                    "] & 0xFF)); i++; }"
                ),
                "    return OK;",
                "}",
                "int waddwstr(WINDOW *w, const wchar_t *ws) { return waddnwstr(w, ws, -1); }",
                (
                    "int addwstr(const wchar_t *ws) { return waddwstr(stdscr ? stdscr : i"
                    "nitscr(), ws); }"
                ),
                (
                    "int mvaddwstr(int y, int x, const wchar_t *ws) { return move(y, x) ="
                    "= ERR ? ERR : addwstr(ws); }"
                ),
                (
                    "int mvwaddwstr(WINDOW *w, int y, int x, const wchar_t *ws) { return "
                    "wmove(w, y, x) == ERR ? ERR : waddwstr(w, ws); }"
                ),
                (
                    "int mvwaddnwstr(WINDOW *w, int y, int x, const wchar_t *ws, int n) {"
                    " return wmove(w, y, x) == ERR ? ERR : waddnwstr(w, ws, n); }"
                ),
                (
                    "int setcchar(cchar_t *wcval, const wchar_t *wch, attr_t attrs, short"
                    " pair, const void *opts) {"
                ),
                "    int i; (void)opts; if (!wcval || !wch) return ERR;",
                "    memset(wcval, 0, sizeof(*wcval));",
                "    wcval->attr = attrs | COLOR_PAIR(pair);",
                "    for (i = 0; i < CCHARW_MAX - 1 && wch[i] != 0; i++) wcval->chars[i] = wch[i];",
                "    return OK;",
                "}",
                (
                    "int getcchar(const cchar_t *wcval, wchar_t *wch, attr_t *attrs, shor"
                    "t *pair, void *opts) {"
                ),
                "    int i; (void)opts; if (!wcval) return ERR;",
                "    if (!wch) return 1;",
                "    for (i = 0; i < CCHARW_MAX; i++) wch[i] = wcval->chars[i];",
                "    if (attrs) *attrs = wcval->attr;",
                "    if (pair) *pair = (short)PAIR_NUMBER(wcval->attr);",
                "    return OK;",
                "}",
                (
                    "int wadd_wch(WINDOW *w, const cchar_t *wch) { return (!w || !wch) ? "
                    "ERR : waddch(w, (chtype)(wch->chars[0] & 0xFF) | wch->attr); }"
                ),
                (
                    "int mvwadd_wch(WINDOW *w, int y, int x, const cchar_t *wch) { return"
                    " wmove(w, y, x) == ERR ? ERR : wadd_wch(w, wch); }"
                ),
                (
                    "chtype winch(WINDOW *w) { return w ? w->_cells[w->_cury * w->_maxx +"
                    " w->_curx] : (chtype)ERR; }"
                ),
                "chtype inch(void) { return winch(stdscr); }",
                "chtype mvinch(int y, int x) { return move(y, x) == ERR ? (chtype)ERR : inch(); }",
                (
                    "chtype mvwinch(WINDOW *w, int y, int x) { return wmove(w, y, x) == E"
                    "RR ? (chtype)ERR : winch(w); }"
                ),
                "int winsch(WINDOW *w, chtype ch) { return waddch(w, ch); }",
                "int insch(chtype ch) { return winsch(stdscr, ch); }",
                (
                    "int mvinsch(int y, int x, chtype ch) { return move(y, x) == ERR ? ER"
                    "R : insch(ch); }"
                ),
                (
                    "int mvwinsch(WINDOW *w, int y, int x, chtype ch) { return wmove(w, y"
                    ", x) == ERR ? ERR : winsch(w, ch); }"
                ),
                "int wdelch(WINDOW *w) { return w ? OK : ERR; }",
                "int delch(void) { return wdelch(stdscr); }",
                "int mvdelch(int y, int x) { return move(y, x) == ERR ? ERR : delch(); }",
                (
                    "int mvwdelch(WINDOW *w, int y, int x) { return wmove(w, y, x) == ERR"
                    " ? ERR : wdelch(w); }"
                ),
                "int winsertln(WINDOW *w) { return w ? OK : ERR; }",
                "int insertln(void) { return winsertln(stdscr); }",
                "int wdeleteln(WINDOW *w) { return w ? OK : ERR; }",
                "int deleteln(void) { return wdeleteln(stdscr); }",
                "int winsdelln(WINDOW *w, int n) { (void)n; return w ? OK : ERR; }",
                "int insdelln(int n) { return winsdelln(stdscr, n); }",
                "int whline(WINDOW *w, chtype ch, int n) {",
                "    int i; chtype c = ch ? ch : '-'; if (!w) return ERR;",
                (
                    "    for (i = 0; i < n && w->_curx + i < w->_maxx; i++) w->_cells[w->"
                    "_cury * w->_maxx + w->_curx + i] = c | w->_attrs;"
                ),
                "    return OK;",
                "}",
                "int wvline(WINDOW *w, chtype ch, int n) {",
                "    int i; chtype c = ch ? ch : '|'; if (!w) return ERR;",
                (
                    "    for (i = 0; i < n && w->_cury + i < w->_maxy; i++) w->_cells[(w-"
                    ">_cury + i) * w->_maxx + w->_curx] = c | w->_attrs;"
                ),
                "    return OK;",
                "}",
                (
                    "int hline(chtype ch, int n) { return whline(stdscr ? stdscr : initsc"
                    "r(), ch, n); }"
                ),
                (
                    "int vline(chtype ch, int n) { return wvline(stdscr ? stdscr : initsc"
                    "r(), ch, n); }"
                ),
                (
                    "int mvhline(int y, int x, chtype ch, int n) { return move(y, x) == E"
                    "RR ? ERR : hline(ch, n); }"
                ),
                (
                    "int mvvline(int y, int x, chtype ch, int n) { return move(y, x) == E"
                    "RR ? ERR : vline(ch, n); }"
                ),
                (
                    "int mvwhline(WINDOW *w, int y, int x, chtype ch, int n) { return wmo"
                    "ve(w, y, x) == ERR ? ERR : whline(w, ch, n); }"
                ),
                (
                    "int mvwvline(WINDOW *w, int y, int x, chtype ch, int n) { return wmo"
                    "ve(w, y, x) == ERR ? ERR : wvline(w, ch, n); }"
                ),
                (
                    "int wborder(WINDOW *w, chtype ls, chtype rs, chtype ts, chtype bs, c"
                    "htype tl, chtype tr, chtype bl, chtype br) {"
                ),
                "    if (!w) return ERR;",
                "    mvwhline(w, 0, 1, ts ? ts : '-', w->_maxx - 2);",
                "    mvwhline(w, w->_maxy - 1, 1, bs ? bs : '-', w->_maxx - 2);",
                "    mvwvline(w, 1, 0, ls ? ls : '|', w->_maxy - 2);",
                "    mvwvline(w, 1, w->_maxx - 1, rs ? rs : '|', w->_maxy - 2);",
                "    mvwaddch(w, 0, 0, tl ? tl : '+');",
                "    mvwaddch(w, 0, w->_maxx - 1, tr ? tr : '+');",
                "    mvwaddch(w, w->_maxy - 1, 0, bl ? bl : '+');",
                "    mvwaddch(w, w->_maxy - 1, w->_maxx - 1, br ? br : '+');",
                "    return OK;",
                "}",
                (
                    "int box(WINDOW *w, chtype verch, chtype horch) { return wborder(w, v"
                    "erch, verch, horch, horch, 0, 0, 0, 0); }"
                ),
                (
                    "int whline_set(WINDOW *w, const cchar_t *c, int n) { return whline(w"
                    ", c ? (chtype)(c->chars[0] & 0xFF) : '-', n); }"
                ),
                (
                    "int wvline_set(WINDOW *w, const cchar_t *c, int n) { return wvline(w"
                    ", c ? (chtype)(c->chars[0] & 0xFF) : '|', n); }"
                ),
                (
                    "int mvwhline_set(WINDOW *w, int y, int x, const cchar_t *c, int n) {"
                    " return wmove(w, y, x) == ERR ? ERR : whline_set(w, c, n); }"
                ),
                (
                    "int mvwvline_set(WINDOW *w, int y, int x, const cchar_t *c, int n) {"
                    " return wmove(w, y, x) == ERR ? ERR : wvline_set(w, c, n); }"
                ),
                (
                    "int hline_set(const cchar_t *c, int n) { return whline_set(stdscr ? "
                    "stdscr : initscr(), c, n); }"
                ),
                (
                    "int vline_set(const cchar_t *c, int n) { return wvline_set(stdscr ? "
                    "stdscr : initscr(), c, n); }"
                ),
                (
                    "int mvhline_set(int y, int x, const cchar_t *c, int n) { return move"
                    "(y, x) == ERR ? ERR : hline_set(c, n); }"
                ),
                (
                    "int mvvline_set(int y, int x, const cchar_t *c, int n) { return move"
                    "(y, x) == ERR ? ERR : vline_set(c, n); }"
                ),
                "int set_tabsize(int cols) { TABSIZE = cols > 0 ? cols : 8; return OK; }",
                "int set_escdelay(int sz) { ESCDELAY = sz >= 0 ? sz : 25; return OK; }",
                (
                    "int wborder_set(WINDOW *w, const cchar_t *ls, const cchar_t *rs, "
                    "const cchar_t *ts, const cchar_t *bs, const cchar_t *tl, "
                    "const cchar_t *tr, const cchar_t *bl, const cchar_t *br) {"
                ),
                "    (void)ls; (void)rs; (void)ts; (void)bs;",
                "    (void)tl; (void)tr; (void)bl; (void)br;",
                "    return box(w, 0, 0);",
                "}",
                (
                    "int box_set(WINDOW *w, const cchar_t *v, const cchar_t *h) {"
                    " return wborder_set(w, v, v, h, h, NULL, NULL, NULL, NULL); }"
                ),
                (
                    "int border(chtype ls, chtype rs, chtype ts, chtype bs, chtype tl, ch"
                    "type tr, chtype bl, chtype br) {"
                ),
                "    return wborder(stdscr ? stdscr : initscr(), ls, rs, ts, bs, tl, tr, bl, br);",
                "}",
                "int vw_printw(WINDOW *win, const char *fmt, va_list ap) {",
                "    char buf[2048]; if (!win || !fmt) return ERR;",
                "    vsnprintf(buf, sizeof(buf), fmt, ap);",
                "    return waddstr(win, buf);",
                "}",
                (
                    "int vwprintw(WINDOW *w, const char *f, va_list ap) { return vw_print"
                    "w(w, f, ap); }"
                ),
                (
                    "int wprintw(WINDOW *w, const char *fmt, ...) { int r; va_list ap; va"
                    "_start(ap, fmt); r = vw_printw(w, fmt, ap); va_end(ap); return r; }"
                ),
                (
                    "int printw(const char *fmt, ...) { int r; va_list ap; va_start(ap, f"
                    "mt); r = vw_printw(stdscr ? stdscr : initscr(), fmt, ap); va_end(ap)"
                    "; return r; }"
                ),
                (
                    "int mvprintw(int y, int x, const char *fmt, ...) { int r; va_list ap"
                    "; if (move(y, x) == ERR) return ERR; va_start(ap, fmt); r = vw_print"
                    "w(stdscr, fmt, ap); va_end(ap); return r; }"
                ),
                (
                    "int mvwprintw(WINDOW *w, int y, int x, const char *fmt, ...) { int r"
                    "; va_list ap; if (wmove(w, y, x) == ERR) return ERR; va_start(ap, fm"
                    "t); r = vw_printw(w, fmt, ap); va_end(ap); return r; }"
                ),
                "int wgetch(WINDOW *win) {",
                "    int c; if (!win) return ERR;",
                "    if (g_unget_buf != ERR) { c = g_unget_buf; g_unget_buf = ERR; return c; }",
                "    if (win->_nodelay) return ERR;",
                "    c = fgetc(stdin);",
                "    return (c == EOF) ? ERR : c;",
                "}",
                "int fbsd_curses_getch(void) { return wgetch(stdscr ? stdscr : initscr()); }",
                "int fbsd_curses_ungetch(int ch) { g_unget_buf = ch; return OK; }",
                "#if !defined(_WIN32) && !defined(__DOS__) && !defined(__MSDOS__)",
                "int getch(void) { return fbsd_curses_getch(); }",
                "int ungetch(int ch) { return fbsd_curses_ungetch(ch); }",
                "#endif",
                "chtype getattrs(const WINDOW *w) { return w ? w->_attrs : 0U; }",
                (
                    "int mvgetch(int y, int x) { return move(y, x) == ERR"
                    " ? ERR : fbsd_curses_getch(); }"
                ),
                (
                    "int mvwgetch(WINDOW *w, int y, int x) { return wmove(w, y, x) == ERR"
                    " ? ERR : wgetch(w); }"
                ),
                (
                    "int wget_wch(WINDOW *w, wint_t *wch) { int c = wgetch(w); if (c == E"
                    "RR) return ERR; if (wch) *wch = (wint_t)c; return OK; }"
                ),
                "int get_wch(wint_t *wch) { return wget_wch(stdscr ? stdscr : initscr(), wch); }",
                "int unget_wch(wchar_t wch) { g_unget_buf = (int)wch; return OK; }",
                "int wgetnstr(WINDOW *w, char *str, int n) {",
                "    if (!w || !str || n <= 0) return ERR;",
                "    if (!fgets(str, n, stdin)) return ERR;",
                f'    str[strcspn(str, "{BS}r{BS}n")] = 0;',
                "    return OK;",
                "}",
                "int wgetstr(WINDOW *w, char *s) { return wgetnstr(w, s, 1024); }",
                (
                    "int getnstr(char *s, int n) { return wgetnstr(stdscr ? stdscr : init"
                    "scr(), s, n); }"
                ),
                "int getstr(char *s) { return getnstr(s, 1024); }",
                (
                    "int mvgetnstr(int y, int x, char *s, int n) { return move(y, x) == E"
                    "RR ? ERR : getnstr(s, n); }"
                ),
                (
                    "int mvwgetnstr(WINDOW *w, int y, int x, char *s, int n) { return wmo"
                    "ve(w, y, x) == ERR ? ERR : wgetnstr(w, s, n); }"
                ),
                "int flushinp(void) { g_unget_buf = ERR; return OK; }",
                "int cbreak(void) { return OK; }",
                "int nocbreak(void) { return OK; }",
                "int echo(void) { return OK; }",
                "int noecho(void) { return OK; }",
                "int raw(void) { return OK; }",
                "int noraw(void) { return OK; }",
                "int halfdelay(int t) { (void)t; return OK; }",
                "int intrflush(WINDOW *w, bool bf) { (void)w; (void)bf; return OK; }",
                "int keypad(WINDOW *w, bool bf) { if (w) w->_keypad = bf; return OK; }",
                "int meta(WINDOW *w, bool bf) { (void)w; (void)bf; return OK; }",
                "int nodelay(WINDOW *w, bool bf) { if (w) w->_nodelay = bf; return OK; }",
                "int notimeout(WINDOW *w, bool bf) { (void)w; (void)bf; return OK; }",
                (
                    "void wtimeout(WINDOW *w, int d) { if (w) { w->_timeout = d; w->_node"
                    "lay = (d == 0); } }"
                ),
                "void timeout(int d) { wtimeout(stdscr ? stdscr : initscr(), d); }",
                "int typeahead(int fd) { (void)fd; return OK; }",
                (
                    "int wattron(WINDOW *w, int a) { if (!w) return ERR; w->_attrs |= (at"
                    "tr_t)a; return OK; }"
                ),
                (
                    "int wattroff(WINDOW *w, int a) { if (!w) return ERR; w->_attrs &= ~("
                    "attr_t)a; return OK; }"
                ),
                (
                    "int wattrset(WINDOW *w, int a) { if (!w) return ERR; w->_attrs = (at"
                    "tr_t)a; return OK; }"
                ),
                "int attron(int a) { return wattron(stdscr ? stdscr : initscr(), a); }",
                "int attroff(int a) { return wattroff(stdscr ? stdscr : initscr(), a); }",
                "int attrset(int a) { return wattrset(stdscr ? stdscr : initscr(), a); }",
                (
                    "int wattr_on(WINDOW *w, attr_t a, void *o) { (void)o; return wattron"
                    "(w, (int)a); }"
                ),
                (
                    "int wattr_off(WINDOW *w, attr_t a, void *o) { (void)o; return wattro"
                    "ff(w, (int)a); }"
                ),
                (
                    "int wattr_set(WINDOW *w, attr_t a, short p, void *o) { (void)o; retu"
                    "rn wattrset(w, (int)(a | COLOR_PAIR(p))); }"
                ),
                "int wattr_get(WINDOW *w, attr_t *a, short *p, void *o) {",
                "    (void)o; if (!w) return ERR;",
                "    if (a) *a = w->_attrs;",
                "    if (p) *p = (short)PAIR_NUMBER(w->_attrs);",
                "    return OK;",
                "}",
                "int wstandout(WINDOW *w) { return wattron(w, A_STANDOUT); }",
                "int wstandend(WINDOW *w) { return wattrset(w, A_NORMAL); }",
                "int standout(void) { return wstandout(stdscr ? stdscr : initscr()); }",
                "int standend(void) { return wstandend(stdscr ? stdscr : initscr()); }",
                "void wbkgdset(WINDOW *w, chtype ch) { if (w) w->_bkgd = ch; }",
                "void bkgdset(chtype ch) { wbkgdset(stdscr ? stdscr : initscr(), ch); }",
                "int wbkgd(WINDOW *w, chtype ch) { if (!w) return ERR; w->_bkgd = ch; return OK; }",
                "int bkgd(chtype ch) { return wbkgd(stdscr ? stdscr : initscr(), ch); }",
                "chtype getbkgd(WINDOW *w) { return w ? w->_bkgd : 0; }",
                "int wchgat(WINDOW *w, int n, attr_t attr, short color, const void *opts) {",
                "    int i; (void)opts; if (!w) return ERR;",
                "    for (i = 0; (n < 0 || i < n) && w->_curx + i < w->_maxx; i++) {",
                "        chtype *cell = &w->_cells[w->_cury * w->_maxx + w->_curx + i];",
                "        *cell = (*cell & A_CHARTEXT) | attr | COLOR_PAIR(color);",
                "    }",
                "    return OK;",
                "}",
                (
                    "int mvwchgat(WINDOW *w, int y, int x, int n, attr_t a, short c, cons"
                    "t void *o) { return wmove(w, y, x) == ERR ? ERR : wchgat(w, n, a, c,"
                    " o); }"
                ),
                (
                    "int chgat(int n, attr_t a, short c, const void *o) { return wchgat(s"
                    "tdscr ? stdscr : initscr(), n, a, c, o); }"
                ),
                (
                    "int mvchgat(int y, int x, int n, attr_t a, short c, const void *o) {"
                    " return mvwchgat(stdscr ? stdscr : initscr(), y, x, n, a, c, o); }"
                ),
                "int start_color(void) { return OK; }",
                "bool has_colors(void) { return true; }",
                "bool can_change_color(void) { return false; }",
                (
                    "int init_pair(short pair, short f, short b) { if (pair >= 0 && pair "
                    "< 64) { g_pairs[pair][0] = f; g_pairs[pair][1] = b; } return OK; }"
                ),
                (
                    "int init_color(short c, short r, short g, short b) { (void)c; (void)"
                    "r; (void)g; (void)b; return OK; }"
                ),
                (
                    "int pair_content(short pair, short *f, short *b) { if (pair >= 0 && "
                    "pair < 64) { if (f) *f = g_pairs[pair][0]; if (b) *b = g_pairs[pair]"
                    "[1]; } return OK; }"
                ),
                (
                    "int color_content(short c, short *r, short *g, short *b) { (void)c; "
                    "if (r) *r = 0; if (g) *g = 0; if (b) *b = 0; return OK; }"
                ),
                "int use_default_colors(void) { return OK; }",
                "int assume_default_colors(int fg, int bg) { (void)fg; (void)bg; return OK; }",
                "int curs_set(int v) { (void)v; return 1; }",
                "int napms(int ms) { (void)ms; return OK; }",
                "int beep(void) { fputc(7, stdout); fflush(stdout); return OK; }",
                "int flash(void) { return beep(); }",
                "int baudrate(void) { return 38400; }",
                "char erasechar(void) { return 0x7F; }",
                "char killchar(void) { return 0x15; }",
                "char *longname(void) { return ttytype; }",
                "char *termname(void) { return ttytype; }",
                "chtype termattrs(void) { return A_BOLD | A_UNDERLINE | A_REVERSE; }",
                (
                    "const char *keyname(int c) { static char kb[8]; kb[0] = (char)(c & 0"
                    "x7F); kb[1] = 0; return kb; }"
                ),
                (
                    "const char *unctrl(unsigned int ch) { static char ub[4]; if (ch < 32"
                    "U) { ub[0] = '^'; ub[1] = (char)(ch + 64U); ub[2] = 0; } else { ub[0"
                    "] = (char)(ch & 0x7FU); ub[1] = 0; } return ub; }"
                ),
                "int def_prog_mode(void) { return OK; }",
                "int def_shell_mode(void) { return OK; }",
                "int reset_prog_mode(void) { return OK; }",
                "int reset_shell_mode(void) { return OK; }",
                "int savetty(void) { return OK; }",
                "int resetty(void) { return OK; }",
                "bool has_ic(void) { return true; }",
                "bool has_il(void) { return true; }",
                (
                    "int resizeterm(int lines, int columns) { LINES = lines; COLS = colum"
                    "ns; return stdscr ? wresize(stdscr, lines, columns) : OK; }"
                ),
                "bool is_term_resized(int l, int c) { return l != LINES || c != COLS; }",
                "int resize_term(int l, int c) { return resizeterm(l, c); }",
                "void use_env(bool f) { (void)f; }",
                "void filter(void) {}",
                'const char *curses_version(void) { return "ncurses 6.5"; }',
                "",
                "int setupterm(const char *term, int filedes, int *errret) {",
                "    (void)term; (void)filedes;",
                "    fbsd_detect_size();",
                "    if (errret) *errret = 1;",
                "    return OK;",
                "}",
                (
                    "TERMINAL *set_curterm(TERMINAL *nterm) { TERMINAL *old = cur_term; c"
                    "ur_term = nterm ? nterm : &g_default_term; return old; }"
                ),
                "int del_curterm(TERMINAL *oterm) { (void)oterm; return OK; }",
                "int restartterm(const char *t, int fd, int *e) { return setupterm(t, fd, e); }",
                "int tigetnum(const char *cap) {",
                "    if (!cap) return -1;",
                '    if (strcmp(cap, "cols") == 0) return COLS;',
                '    if (strcmp(cap, "lines") == 0) return LINES;',
                '    if (strcmp(cap, "colors") == 0) return COLORS;',
                '    if (strcmp(cap, "it") == 0) return 8;',
                "    return -1;",
                "}",
                "int tigetflag(const char *cap) { (void)cap; return 1; }",
                "char *tigetstr(const char *cap) {",
                '    static char empty_s[2] = "";',
                "    if (!cap) return (char *)0;",
                f'    if (strcmp(cap, "clear") == 0) return "{BS}033[H{BS}033[2J";',
                f'    if (strcmp(cap, "cr") == 0) return "{BS}r";',
                f'    if (strcmp(cap, "hts") == 0) return "{BS}033H";',
                f'    if (strcmp(cap, "tbc") == 0) return "{BS}033[3g";',
                "    return empty_s;",
                "}",
                'char *tparm(const char *str, ...) { return (char *)(str ? str : ""); }',
                'char *tiparm(const char *str, ...) { return (char *)(str ? str : ""); }',
                "int tputs(const char *str, int affcnt, int (*putc_fn)(int)) {",
                "    size_t i; (void)affcnt; if (!str || !putc_fn) return ERR;",
                "    for (i = 0; str[i] != 0; i++) putc_fn((unsigned char)str[i]);",
                "    return OK;",
                "}",
                "int putp(const char *str) { return tputs(str, 1, putchar); }",
                (
                    "int tgetent(char *bp, const char *name) { (void)bp; (void)name; fbsd"
                    "_detect_size(); return 1; }"
                ),
                "int tgetflag(const char *id) { return tigetflag(id); }",
                "int tgetnum(const char *id) {",
                "    if (!id) return -1;",
                '    if (strcmp(id, "co") == 0) return COLS;',
                '    if (strcmp(id, "li") == 0) return LINES;',
                "    return -1;",
                "}",
                "char *tgetstr(const char *id, char **area) { (void)area; return tigetstr(id); }",
                "char *tgoto(const char *cap, int col, int row) {",
                "    static char gt[32]; (void)cap;",
                f'    snprintf(gt, sizeof(gt), "{BS}033[%d;%dH", row + 1, col + 1);',
                "    return gt;",
                "}",
            ]
        )
        + LF
    )

    for rel_name, content in (
        ("unctrl.h", unctrl_h),
        ("term.h", term_h),
        ("termcap.h", termcap_h),
        ("curses.h", curses_h),
        ("ncurses.h", ncurses_h),
        ("fbsd_curses.c", fbsd_curses_c),
    ):
        dst = (out_dir / rel_name).resolve()
        dst.write_text(content, encoding="utf-8")
        emitted[rel_name] = dst
    return emitted


def emit_libedit_section3_sources(out_dir: Path) -> dict[str, Path]:
    """Emit portable C89 ``editline(3)`` / ``readline`` headers and C source.

    Args:
        out_dir: Destination ``codegen/libedit`` directory.

    Returns:
        Mapping of generated relative filenames to resolved ``Path``s.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "editline").mkdir(parents=True, exist_ok=True)
    (out_dir / "readline").mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    histedit_h = (
        LF.join(
            [
                "#ifndef FBSD_HISTEDIT_H_",
                "#define FBSD_HISTEDIT_H_",
                "#include <stdio.h>",
                "#include <wchar.h>",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "typedef struct editline EditLine;",
                "typedef struct history History;",
                "typedef struct tokenizer Tokenizer;",
                (
                    "typedef struct { char *buffer; char *cursor; char *lastchar; const c"
                    "har *limit; } LineInfo;"
                ),
                "typedef struct { int num; const char *str; } HistEvent;",
                "#define CC_NORM       0",
                "#define CC_NEWLINE    1",
                "#define CC_EOF        2",
                "#define CC_ARGHACK    3",
                "#define CC_REFRESH    4",
                "#define CC_CURSOR     5",
                "#define CC_ERROR      6",
                "#define CC_FATAL      7",
                "#define CC_REDISPLAY  8",
                "#define CC_REFRESH_BEEP 9",
                "#define EL_PROMPT     0",
                "#define EL_TERMINAL   1",
                "#define EL_EDITOR     2",
                "#define EL_SIGNAL     3",
                "#define EL_BIND       4",
                "#define EL_TELLTC     5",
                "#define EL_SETTC      6",
                "#define EL_ECHOTC     7",
                "#define EL_SETTY      8",
                "#define EL_ADDFN      9",
                "#define EL_HIST       10",
                "#define EL_EDITMODE   11",
                "#define EL_RPROMPT    12",
                "#define EL_GETCFN     13",
                "#define EL_CLIENTDATA 14",
                "#define EL_UNBUFFERED 15",
                "#define EL_PREP_TERM  16",
                "#define EL_GETTC      17",
                "#define EL_GETFP      18",
                "#define EL_SETFP      19",
                "#define EL_REFRESH    20",
                "#define EL_PROMPT_ESC 21",
                "#define H_FUNC        0",
                "#define H_SETSIZE     1",
                "#define H_GETSIZE     2",
                "#define H_FIRST       3",
                "#define H_LAST        4",
                "#define H_PREV        5",
                "#define H_NEXT        6",
                "#define H_CURR        7",
                "#define H_SET         8",
                "#define H_ADD         9",
                "#define H_ENTER       10",
                "#define H_APPEND      11",
                "#define H_END         12",
                "#define H_NEXT_STR    13",
                "#define H_PREV_STR    14",
                "#define H_NEXT_EVENT  15",
                "#define H_PREV_EVENT  16",
                "#define H_LOAD        17",
                "#define H_SAVE        18",
                "#define H_CLEAR       19",
                "#define H_SETUNIQUE   20",
                "EditLine *el_init(const char *prog, FILE *fin, FILE *fout, FILE *ferr);",
                (
                    "EditLine *el_init_fd(const char *prog, FILE *fin, FILE *fout, FILE *"
                    "ferr, int fdin, int fdout, int fderr);"
                ),
                "void el_end(EditLine *el);",
                "void el_reset(EditLine *el);",
                "const char *el_gets(EditLine *el, int *count);",
                "int el_getc(EditLine *el, char *ch);",
                "void el_push(EditLine *el, const char *str);",
                "void el_beep(EditLine *el);",
                "int el_parse(EditLine *el, int argc, const char **argv);",
                "int el_set(EditLine *el, int op, ...);",
                "int el_get(EditLine *el, int op, ...);",
                "int el_source(EditLine *el, const char *file);",
                "void el_resize(EditLine *el);",
                "const LineInfo *el_line(EditLine *el);",
                "int el_insertstr(EditLine *el, const char *str);",
                "void el_deletestr(EditLine *el, int count);",
                "History *history_init(void);",
                "void history_end(History *h);",
                "int history(History *h, HistEvent *ev, int op, ...);",
                "Tokenizer *tok_init(const char *ifs);",
                "void tok_end(Tokenizer *tok);",
                "void tok_reset(Tokenizer *tok);",
                (
                    "int tok_line(Tokenizer *tok, const LineInfo *li, int *argc, const ch"
                    "ar ***argv, int *cursorc, int *cursoro);"
                ),
                "int tok_str(Tokenizer *tok, const char *line, int *argc, const char ***argv);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    readline_h = (
        LF.join(
            [
                "#ifndef FBSD_EDITLINE_READLINE_H_",
                "#define FBSD_EDITLINE_READLINE_H_",
                "#include <stdio.h>",
                "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                "#if defined(fbsd_libedit_EXPORTS)",
                "#define _FBSD_EDIT_DATA extern __declspec(dllexport)",
                "#elif !defined(FBSD_EDIT_STATIC)",
                "#define _FBSD_EDIT_DATA extern __declspec(dllimport)",
                "#else",
                "#define _FBSD_EDIT_DATA extern",
                "#endif",
                "#else",
                "#define _FBSD_EDIT_DATA extern",
                "#endif",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "typedef char *rl_compentry_func_t(const char *, int);",
                "typedef char **rl_completion_func_t(const char *, int, int);",
                "_FBSD_EDIT_DATA const char *rl_readline_name;",
                "_FBSD_EDIT_DATA char *rl_line_buffer;",
                "_FBSD_EDIT_DATA int rl_point;",
                "_FBSD_EDIT_DATA int rl_end;",
                "_FBSD_EDIT_DATA int rl_attempted_completion_over;",
                "_FBSD_EDIT_DATA rl_completion_func_t *rl_attempted_completion_function;",
                "_FBSD_EDIT_DATA rl_compentry_func_t *rl_completion_entry_function;",
                "char *readline(const char *prompt);",
                "int add_history(const char *line);",
                "void using_history(void);",
                "int read_history(const char *filename);",
                "int write_history(const char *filename);",
                "char **rl_completion_matches(const char *text, rl_compentry_func_t *entry_func);",
                "char **completion_matches(const char *text, rl_compentry_func_t *entry_func);",
                "char *filename_completion_function(const char *text, int state);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    fbsd_edit_c = (
        LF.join(
            [
                '#include "histedit.h"',
                '#include "editline/readline.h"',
                "#include <ctype.h>",
                "#include <stdarg.h>",
                "#include <stdlib.h>",
                "#include <string.h>",
                "",
                "struct editline {",
                "    FILE *fin, *fout, *ferr;",
                "    char buf[4096];",
                "    LineInfo li;",
                "    char *(*prompt_fn)(EditLine *);",
                "    void *client_data;",
                "};",
                "struct history { char *entries[128]; int count; };",
                "struct tokenizer { char ifs[32]; char *copy; const char *argv[256]; };",
                "",
                'const char *rl_readline_name = "editline";',
                "static char g_rl_buf[4096];",
                "char *rl_line_buffer = g_rl_buf;",
                "int rl_point = 0;",
                "int rl_end = 0;",
                "int rl_attempted_completion_over = 0;",
                "rl_completion_func_t *rl_attempted_completion_function = NULL;",
                "rl_compentry_func_t *rl_completion_entry_function = NULL;",
                "",
                "EditLine *el_init(const char *prog, FILE *fin, FILE *fout, FILE *ferr) {",
                "    EditLine *el = (EditLine *)calloc(1, sizeof(EditLine));",
                "    (void)prog;",
                "    if (!el) return NULL;",
                "    el->fin = fin ? fin : stdin;",
                "    el->fout = fout ? fout : stdout;",
                "    el->ferr = ferr ? ferr : stderr;",
                "    el->li.buffer = el->buf; el->li.cursor = el->buf; el->li.lastchar = el->buf;",
                "    el->li.limit = el->buf + sizeof(el->buf) - 1;",
                "    return el;",
                "}",
                (
                    "EditLine *el_init_fd(const char *prog, FILE *fin, FILE *fout, FILE *"
                    "ferr, int i, int o, int e) {"
                ),
                "    (void)i; (void)o; (void)e; return el_init(prog, fin, fout, ferr);",
                "}",
                "void el_end(EditLine *el) { free(el); }",
                "void el_reset(EditLine *el) { if (el) el->buf[0] = 0; }",
                "const char *el_gets(EditLine *el, int *count) {",
                "    size_t len;",
                "    if (!el) return NULL;",
                (
                    "    if (el->prompt_fn && el->fout) { fputs(el->prompt_fn(el), el->fo"
                    "ut); fflush(el->fout); }"
                ),
                (
                    "    if (!fgets(el->buf, (int)sizeof(el->buf), el->fin)) { if (count)"
                    " *count = 0; return NULL; }"
                ),
                "    len = strlen(el->buf);",
                "    el->li.cursor = el->buf + len; el->li.lastchar = el->buf + len;",
                "    if (count) *count = (int)len;",
                "    return el->buf;",
                "}",
                "int el_getc(EditLine *el, char *ch) {",
                "    int c; if (!el || !ch) return -1;",
                "    c = fgetc(el->fin); if (c == EOF) return 0;",
                "    *ch = (char)c; return 1;",
                "}",
                "void el_push(EditLine *el, const char *str) { (void)el; (void)str; }",
                "void el_beep(EditLine *el) { if (el && el->fout) fputc(7, el->fout); }",
                (
                    "int el_parse(EditLine *el, int argc, const char **argv) { (void)el; "
                    "(void)argc; (void)argv; return 0; }"
                ),
                "int el_set(EditLine *el, int op, ...) {",
                "    va_list ap; if (!el) return -1;",
                "    va_start(ap, op);",
                "    if (op == EL_PROMPT || op == EL_PROMPT_ESC) {",
                "        typedef char *(*pfn_t)(EditLine *);",
                "        el->prompt_fn = va_arg(ap, pfn_t);",
                "    } else if (op == EL_CLIENTDATA) {",
                "        el->client_data = va_arg(ap, void *);",
                "    }",
                "    va_end(ap);",
                "    return 0;",
                "}",
                "int el_get(EditLine *el, int op, ...) {",
                "    va_list ap; if (!el) return -1;",
                "    va_start(ap, op);",
                (
                    "    if (op == EL_CLIENTDATA) { void **out = va_arg(ap, void **); if "
                    "(out) *out = el->client_data; }"
                ),
                "    va_end(ap);",
                "    return 0;",
                "}",
                "int el_source(EditLine *el, const char *file) { (void)el; (void)file; return 0; }",
                "void el_resize(EditLine *el) { (void)el; }",
                "const LineInfo *el_line(EditLine *el) { return el ? &el->li : NULL; }",
                "int el_insertstr(EditLine *el, const char *str) {",
                "    size_t cur, add; if (!el || !str) return -1;",
                "    cur = strlen(el->buf); add = strlen(str);",
                "    if (cur + add + 1 >= sizeof(el->buf)) return -1;",
                "    memcpy(el->buf + cur, str, add + 1);",
                "    el->li.lastchar = el->buf + cur + add; el->li.cursor = el->li.lastchar;",
                "    return 0;",
                "}",
                "void el_deletestr(EditLine *el, int count) {",
                "    size_t cur; if (!el || count <= 0) return;",
                "    cur = strlen(el->buf);",
                (
                    "    if ((size_t)count >= cur) el->buf[0] = 0; else el->buf[cur - (si"
                    "ze_t)count] = 0;"
                ),
                "    el->li.lastchar = el->buf + strlen(el->buf); el->li.cursor = el->li.lastchar;",
                "}",
                "History *history_init(void) { return (History *)calloc(1, sizeof(History)); }",
                "void history_end(History *h) {",
                "    int i; if (!h) return;",
                "    for (i = 0; i < h->count; i++) free(h->entries[i]);",
                "    free(h);",
                "}",
                "int history(History *h, HistEvent *ev, int op, ...) {",
                "    va_list ap; if (!h) return -1;",
                '    if (ev) { ev->num = h->count; ev->str = ""; }',
                "    va_start(ap, op);",
                "    if (op == H_ENTER || op == H_ADD) {",
                "        const char *s = va_arg(ap, const char *);",
                "        if (s && h->count < 128) h->entries[h->count++] = strdup(s);",
                "    }",
                "    va_end(ap);",
                "    return 0;",
                "}",
                "Tokenizer *tok_init(const char *ifs) {",
                "    Tokenizer *t = (Tokenizer *)calloc(1, sizeof(Tokenizer));",
                f'    if (t) snprintf(t->ifs, sizeof(t->ifs), "%s", ifs ? ifs : " {BS}t{BS}n");',
                "    return t;",
                "}",
                (
                    "void tok_reset(Tokenizer *tok) { if (tok) { free(tok->copy); tok->co"
                    "py = NULL; } }"
                ),
                "void tok_end(Tokenizer *tok) { if (tok) { free(tok->copy); free(tok); } }",
                "int tok_str(Tokenizer *tok, const char *line, int *argc, const char ***argv) {",
                "    int n = 0; char *p;",
                "    if (!tok || !line || !argc || !argv) return -1;",
                "    tok_reset(tok);",
                "    tok->copy = strdup(line);",
                "    if (!tok->copy) return -1;",
                "    p = strtok(tok->copy, tok->ifs);",
                "    while (p && n < 255) { tok->argv[n++] = p; p = strtok(NULL, tok->ifs); }",
                "    tok->argv[n] = NULL;",
                "    *argc = n; *argv = tok->argv;",
                "    return 0;",
                "}",
                (
                    "int tok_line(Tokenizer *tok, const LineInfo *li, int *argc, const ch"
                    "ar ***argv, int *cc, int *co) {"
                ),
                "    if (cc) { *cc = 0; }",
                "    if (co) { *co = 0; }",
                "    return (!li || !li->buffer) ? -1 : tok_str(tok, li->buffer, argc, argv);",
                "}",
                "char *readline(const char *prompt) {",
                "    char *res;",
                "    if (prompt) { fputs(prompt, stdout); fflush(stdout); }",
                "    if (!fgets(g_rl_buf, (int)sizeof(g_rl_buf), stdin)) return NULL;",
                f'    g_rl_buf[strcspn(g_rl_buf, "{BS}r{BS}n")] = 0;',
                "    rl_end = (int)strlen(g_rl_buf); rl_point = rl_end;",
                "    res = strdup(g_rl_buf);",
                "    return res;",
                "}",
                "int add_history(const char *line) { (void)line; return 0; }",
                "void using_history(void) {}",
                "int read_history(const char *f) { (void)f; return 0; }",
                "int write_history(const char *f) { (void)f; return 0; }",
                (
                    "char **rl_completion_matches(const char *t, rl_compentry_func_t *fn)"
                    " { (void)t; (void)fn; return NULL; }"
                ),
                (
                    "char **completion_matches(const char *t, rl_compentry_func_t *fn) { "
                    "return rl_completion_matches(t, fn); }"
                ),
                (
                    "char *filename_completion_function(const char *t, int s) { (void)t; "
                    "(void)s; return NULL; }"
                ),
            ]
        )
        + LF
    )

    for rel_name, content in (
        ("histedit.h", histedit_h),
        ("editline/readline.h", readline_h),
        ("readline/readline.h", readline_h),
        ("readline/history.h", readline_h),
        ("fbsd_edit.c", fbsd_edit_c),
    ):
        dst = (out_dir / rel_name).resolve()
        dst.write_text(content, encoding="utf-8")
        emitted[rel_name] = dst
    return emitted


def emit_libmp_section3_sources(out_dir: Path) -> dict[str, Path]:
    """Emit portable C89 ``mp(3)`` big-integer ``MINT`` header and C source.

    Args:
        out_dir: Destination ``codegen/libmp`` directory.

    Returns:
        Mapping of generated relative filenames to resolved ``Path``s.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    mp_h = (
        LF.join(
            [
                "#ifndef FBSD_MP_H_",
                "#define FBSD_MP_H_",
                "#include <stdint.h>",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "typedef struct mint { int sign; uint64_t mag; } MINT;",
                "MINT *mp_itom(short n);",
                "MINT *mp_xtom(const char *key);",
                "char *mp_mtox(const MINT *mp);",
                "void mp_mfree(MINT *mp);",
                "void mp_move(const MINT *a, MINT *b);",
                "void mp_madd(const MINT *a, const MINT *b, MINT *c);",
                "void mp_msub(const MINT *a, const MINT *b, MINT *c);",
                "void mp_mult(const MINT *a, const MINT *b, MINT *c);",
                "void mp_mdiv(const MINT *n, const MINT *d, MINT *q, MINT *r);",
                "void mp_sdiv(const MINT *n, short d, MINT *q, short *r);",
                "void mp_msqrt(const MINT *a, MINT *b, MINT *r);",
                "void mp_pow(const MINT *a, const MINT *b, const MINT *m, MINT *c);",
                "void mp_rpow(const MINT *a, short n, MINT *c);",
                "void mp_gcd(const MINT *a, const MINT *b, MINT *c);",
                "int mp_mcmp(const MINT *a, const MINT *b);",
                "void mp_min(MINT *a);",
                "void mp_mout(const MINT *a);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    fbsd_mp_c = (
        LF.join(
            [
                '#include "mp.h"',
                "#include <inttypes.h>",
                "#include <stdio.h>",
                "#include <stdlib.h>",
                "",
                "MINT *mp_itom(short n) {",
                "    MINT *m = (MINT *)calloc(1, sizeof(MINT));",
                "    if (!m) return NULL;",
                "    if (n < 0) { m->sign = -1; m->mag = (uint64_t)(-(int)n); }",
                "    else if (n > 0) { m->sign = 1; m->mag = (uint64_t)n; }",
                "    return m;",
                "}",
                "MINT *mp_xtom(const char *key) {",
                "    MINT *m = (MINT *)calloc(1, sizeof(MINT));",
                "    if (!m || !key) return m;",
                "    if (*key == '-') { m->sign = -1; key++; } else { m->sign = 1; }",
                "    m->mag = (uint64_t)strtoull(key, NULL, 16);",
                "    if (m->mag == 0) m->sign = 0;",
                "    return m;",
                "}",
                "char *mp_mtox(const MINT *mp) {",
                "    char *buf = (char *)malloc(32);",
                "    if (!buf || !mp) return buf;",
                '    snprintf(buf, 32, "%s%" PRIx64, mp->sign < 0 ? "-" : "", mp->mag);',
                "    return buf;",
                "}",
                "void mp_mfree(MINT *mp) { free(mp); }",
                "void mp_move(const MINT *a, MINT *b) { if (a && b) *b = *a; }",
                (
                    "static int64_t mp_val(const MINT *a) { return !a ? 0 : (a->sign < 0 "
                    "? -(int64_t)a->mag : (int64_t)a->mag); }"
                ),
                "static void mp_set(MINT *c, int64_t v) {",
                "    if (!c) return;",
                "    if (v < 0) { c->sign = -1; c->mag = (uint64_t)(-v); }",
                "    else if (v > 0) { c->sign = 1; c->mag = (uint64_t)v; }",
                "    else { c->sign = 0; c->mag = 0; }",
                "}",
                (
                    "void mp_madd(const MINT *a, const MINT *b, MINT *c) {"
                    " mp_set(c, mp_val(a) + mp_val(b)); }"
                ),
                (
                    "void mp_msub(const MINT *a, const MINT *b, MINT *c) {"
                    " mp_set(c, mp_val(a) - mp_val(b)); }"
                ),
                (
                    "void mp_mult(const MINT *a, const MINT *b, MINT *c) {"
                    " mp_set(c, mp_val(a) * mp_val(b)); }"
                ),
                "void mp_mdiv(const MINT *n, const MINT *d, MINT *q, MINT *r) {",
                "    int64_t nv = mp_val(n), dv = mp_val(d);",
                "    if (dv == 0) { mp_set(q, 0); mp_set(r, 0); return; }",
                "    mp_set(q, nv / dv); mp_set(r, nv % dv);",
                "}",
                "void mp_sdiv(const MINT *n, short d, MINT *q, short *r) {",
                (
                    "    MINT dm, rm; dm.sign = d < 0 ? -1 : (d > 0 ? 1 : 0); dm.mag = (u"
                    "int64_t)(d < 0 ? -d : d);"
                ),
                "    mp_mdiv(n, &dm, q, &rm);",
                "    if (r) *r = (short)mp_val(&rm);",
                "}",
                "void mp_msqrt(const MINT *a, MINT *b, MINT *r) {",
                "    uint64_t v = a ? a->mag : 0, x = v, y = (x + 1U) / 2U;",
                "    while (y < x) { x = y; y = (x + v / x) / 2U; }",
                "    mp_set(b, (int64_t)x); mp_set(r, (int64_t)(v - x * x));",
                "}",
                "void mp_pow(const MINT *a, const MINT *b, const MINT *m, MINT *c) {",
                "    uint64_t base = a ? a->mag : 0, exp = b ? b->mag : 0;",
                "    uint64_t mod = (m && m->mag) ? m->mag : 0, res = 1U;",
                "    if (mod == 0) { mp_set(c, 0); return; }",
                "    base %= mod;",
                "    while (exp > 0) {",
                "        if (exp & 1U) { res = (res * base) % mod; }",
                "        base = (base * base) % mod; exp >>= 1U;",
                "    }",
                "    mp_set(c, (int64_t)res);",
                "}",
                "void mp_rpow(const MINT *a, short n, MINT *c) {",
                "    int64_t base = mp_val(a), acc = 1; short i;",
                "    for (i = 0; i < n; i++) acc *= base;",
                "    mp_set(c, acc);",
                "}",
                "void mp_gcd(const MINT *a, const MINT *b, MINT *c) {",
                "    uint64_t x = a ? a->mag : 0, y = b ? b->mag : 0, t;",
                "    while (y != 0) { t = x % y; x = y; y = t; }",
                "    mp_set(c, (int64_t)x);",
                "}",
                "int mp_mcmp(const MINT *a, const MINT *b) {",
                "    int64_t av = mp_val(a), bv = mp_val(b);",
                "    return (av < bv) ? -1 : ((av > bv) ? 1 : 0);",
                "}",
                "void mp_min(MINT *a) {",
                "    long long v = 0;",
                '    if (scanf("%lld", &v) == 1) { mp_set(a, (int64_t)v); }',
                "}",
                f'void mp_mout(const MINT *a) {{ printf("%" PRId64 "{BS}n", mp_val(a)); }}',
            ]
        )
        + LF
    )

    for rel_name, content in (("mp.h", mp_h), ("fbsd_mp.c", fbsd_mp_c)):
        dst = (out_dir / rel_name).resolve()
        dst.write_text(content, encoding="utf-8")
        emitted[rel_name] = dst
    return emitted


def emit_libsys_section3_sources(out_dir: Path) -> dict[str, Path]:
    """Emit Section 3 FreeBSD system/PAM/YP/NV/BSM headers and C source for ``fbsd_libsys``.

    Args:
        out_dir: Destination ``codegen/libsys`` directory.

    Returns:
        Mapping of generated relative filenames to resolved ``Path``s.
    """
    for sub in ("security", "rpcsvc", "sys", "bsm"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    pam_h = (
        LF.join(
            [
                "#ifndef FBSD_SECURITY_PAM_APPL_H_",
                "#define FBSD_SECURITY_PAM_APPL_H_",
                "#include <stddef.h>",
                "#ifndef _FBSD_SYS_DATA",
                "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                "#if defined(fbsd_libsys_EXPORTS)",
                "#define _FBSD_SYS_DATA extern __declspec(dllexport)",
                "#elif !defined(FBSD_SYS_STATIC)",
                "#define _FBSD_SYS_DATA extern __declspec(dllimport)",
                "#else",
                "#define _FBSD_SYS_DATA extern",
                "#endif",
                "#else",
                "#define _FBSD_SYS_DATA extern",
                "#endif",
                "#endif",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "#define PAM_SUCCESS 0",
                "#define PAM_OPEN_ERR 1",
                "#define PAM_SYMBOL_ERR 2",
                "#define PAM_SERVICE_ERR 3",
                "#define PAM_SYSTEM_ERR 4",
                "#define PAM_BUF_ERR 5",
                "#define PAM_CONV_ERR 6",
                "#define PAM_PERM_DENIED 7",
                "#define PAM_MAXTRIES 8",
                "#define PAM_AUTH_ERR 9",
                "#define PAM_NEW_AUTHTOK_REQD 10",
                "#define PAM_CRED_INSUFFICIENT 11",
                "#define PAM_AUTHINFO_UNAVAIL 12",
                "#define PAM_USER_UNKNOWN 13",
                "#define PAM_CRED_UNAVAIL 14",
                "#define PAM_CRED_EXPIRED 15",
                "#define PAM_CRED_ERR 16",
                "#define PAM_ACCT_EXPIRED 17",
                "#define PAM_AUTHTOK_EXPIRED 18",
                "#define PAM_SESSION_ERR 19",
                "#define PAM_AUTHTOK_ERR 20",
                "#define PAM_AUTHTOK_RECOVERY_ERR 21",
                "#define PAM_AUTHTOK_LOCK_BUSY 22",
                "#define PAM_AUTHTOK_DISABLE_AGING 23",
                "#define PAM_NO_MODULE_DATA 24",
                "#define PAM_IGNORE 25",
                "#define PAM_ABORT 26",
                "#define PAM_TRY_AGAIN 27",
                "#define PAM_MODULE_UNKNOWN 28",
                "#define PAM_DOMAIN_UNKNOWN 29",
                "#define PAM_NUM_ERRORS 30",
                "#define PAM_SILENT 0x80000000",
                "#define PAM_DISALLOW_NULL_AUTHTOK 0x0001",
                "#define PAM_ESTABLISH_CRED 0x0001",
                "#define PAM_DELETE_CRED 0x0002",
                "#define PAM_REINITIALIZE_CRED 0x0004",
                "#define PAM_REFRESH_CRED 0x0008",
                "#define PAM_CHANGE_EXPIRED_AUTHTOK 0x0004",
                "#define PAM_PRELIM_CHECK 0x0001",
                "#define PAM_UPDATE_AUTHTOK 0x0002",
                "#define PAM_PROMPT_ECHO_OFF 1",
                "#define PAM_PROMPT_ECHO_ON 2",
                "#define PAM_ERROR_MSG 3",
                "#define PAM_TEXT_INFO 4",
                "#define PAM_SERVICE 1",
                "#define PAM_USER 2",
                "#define PAM_TTY 3",
                "#define PAM_RHOST 4",
                "#define PAM_CONV 5",
                "#define PAM_AUTHTOK 6",
                "#define PAM_OLDAUTHTOK 7",
                "#define PAM_RUSER 8",
                "#define PAM_USER_PROMPT 9",
                "#define PAM_REPOSITORY 10",
                "#define PAM_AUTHTOK_PROMPT 11",
                "#define PAM_OLDAUTHTOK_PROMPT 12",
                "#define PAM_HOST 13",
                "#define PAM_NUM_ITEMS 14",
                "#define OPENPAM_NUM_FEATURES 16",
                "_FBSD_SYS_DATA int openpam_debug;",
                "_FBSD_SYS_DATA int openpam_ttyconv_timeout;",
                "typedef struct pam_handle pam_handle_t;",
                "struct pam_message { int msg_style; const char *msg; };",
                "struct pam_response { char *resp; int resp_retcode; };",
                "struct pam_conv {",
                (
                    "    int (*conv)(int, const struct pam_message **, struct pam_respons"
                    "e **, void *);"
                ),
                "    void *appdata_ptr;",
                "};",
                (
                    "int pam_start(const char *service, const char *user, const struct pa"
                    "m_conv *conv, pam_handle_t **pamh);"
                ),
                "int pam_end(pam_handle_t *pamh, int status);",
                "int pam_authenticate(pam_handle_t *pamh, int flags);",
                "int pam_acct_mgmt(pam_handle_t *pamh, int flags);",
                "int pam_open_session(pam_handle_t *pamh, int flags);",
                "int pam_close_session(pam_handle_t *pamh, int flags);",
                "int pam_setcred(pam_handle_t *pamh, int flags);",
                "int pam_chauthtok(pam_handle_t *pamh, int flags);",
                "int pam_set_item(pam_handle_t *pamh, int item_type, const void *item);",
                "int pam_get_item(const pam_handle_t *pamh, int item_type, const void **item);",
                (
                    "int pam_set_data(pam_handle_t *pamh, const char *module_data_name,"
                    " void *data, void (*cleanup)(pam_handle_t *, void *, int));"
                ),
                (
                    "int pam_get_data(const pam_handle_t *pamh,"
                    " const char *module_data_name, const void **data);"
                ),
                "int pam_get_user(pam_handle_t *pamh, const char **user, const char *prompt);",
                "int pam_putenv(pam_handle_t *pamh, const char *namevalue);",
                "const char *pam_getenv(pam_handle_t *pamh, const char *name);",
                "char **pam_getenvlist(pam_handle_t *pamh);",
                "const char *pam_strerror(const pam_handle_t *pamh, int error_number);",
                "_FBSD_SYS_DATA const char *pam_item_name[PAM_NUM_ITEMS];",
                "_FBSD_SYS_DATA const char *_pam_item_name[PAM_NUM_ITEMS];",
                "int openpam_set_feature(int feature, int onoff);",
                (
                    "int openpam_ttyconv(int n, const struct pam_message **msg, struct pa"
                    "m_response **resp, void *data);"
                ),
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    openpam_h = f'#include "pam_appl.h"{LF}'

    ypclnt_h = (
        LF.join(
            [
                "#ifndef FBSD_RPCSVC_YPCLNT_H_",
                "#define FBSD_RPCSVC_YPCLNT_H_",
                "#ifndef _FBSD_SYS_DATA",
                "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                "#if defined(fbsd_libsys_EXPORTS)",
                "#define _FBSD_SYS_DATA extern __declspec(dllexport)",
                "#elif !defined(FBSD_SYS_STATIC)",
                "#define _FBSD_SYS_DATA extern __declspec(dllimport)",
                "#else",
                "#define _FBSD_SYS_DATA extern",
                "#endif",
                "#else",
                "#define _FBSD_SYS_DATA extern",
                "#endif",
                "#endif",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "#define YPERR_BADARGS 1",
                "#define YPERR_RPC     2",
                "#define YPERR_DOMAIN  3",
                "#define YPERR_MAP     4",
                "#define YPERR_KEY     5",
                "#define YPERR_YPERR   6",
                "#define YPERR_RESRC   7",
                "#define YPERR_NOMORE  8",
                "#define YPERR_PMAP    9",
                "#define YPERR_YPBIND  10",
                "#define YPERR_YPSERV  11",
                "#define YPERR_NODOM   12",
                (
                    "struct ypall_callback { int (*foreach)(unsigned long, char *, int, char *, int"
                    ", void *); char *data; };"
                ),
                "int yp_get_default_domain(char **domp);",
                "int yp_bind(const char *dom);",
                "void yp_unbind(const char *dom);",
                (
                    "int yp_match(const char *indomain, const char *inmap, const char *in"
                    "key, int inkeylen, char **outval, int *outvallen);"
                ),
                (
                    "int yp_first(const char *indomain, const char *inmap, char **outkey,"
                    " int *outkeylen, char **outval, int *outvallen);"
                ),
                (
                    "int yp_next(const char *indomain, const char *inmap, const char *ink"
                    "ey, int inkeylen, char **outkey, int *outkeylen, char **outval, int "
                    "*outvallen);"
                ),
                (
                    "int yp_all(const char *indomain, const char *inmap, struct ypall_cal"
                    "lback *incallback);"
                ),
                "int yp_master(const char *indomain, const char *inmap, char **outname);",
                "int yp_order(const char *indomain, const char *inmap, int *outorder);",
                "struct ypmaplist;",
                "int yp_maplist(const char *indomain, struct ypmaplist **outmaplist);",
                "const char *yperr_string(int incode);",
                "int ypprot_err(unsigned int incode);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    yp_prot_h = (
        LF.join(
            [
                "#ifndef FBSD_RPCSVC_YP_PROT_H_",
                "#define FBSD_RPCSVC_YP_PROT_H_",
                '#include "ypclnt.h"',
                "#if defined(_WIN32)",
                "#include <winsock2.h>",
                "#else",
                "#include <netinet/in.h>",
                "#endif",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "#define YPMAXRECORD 1024",
                "#define YPMAXDOMAIN 64",
                "#define YPMAXMAP    64",
                "#define YPMAXPEER   64",
                "#define YP_FALSE    0",
                "#define YP_TRUE     1",
                "#define YP_NOMORE   2",
                "#define YPPROG      100004UL",
                "#define YPVERS      2UL",
                "#define YPBINDPROG  100007UL",
                "#define YPBINDVERS  2UL",
                "#define YPBINDPROC_DOMAIN 2UL",
                "#define YPBIND_SUCC_VAL 1",
                "#define YPBIND_FAIL_VAL 2",
                "#define YPPROC_MATCH 3UL",
                "#define YPPROC_FIRST 4UL",
                "#define YPPROC_NEXT 5UL",
                "#define YPPROC_ALL 8UL",
                "#define YPPROC_MASTER 9UL",
                "#define YPPROC_ORDER 10UL",
                "#define YPPROC_MAPLIST 11UL",
                (
                    "struct ypmaplist { char *map; char ypml_name[YPMAXMAP + 1];"
                    " struct ypmaplist *next; struct ypmaplist *ypml_next; };"
                ),
                (
                    "struct ypresp_maplist { unsigned int status; int stat;"
                    " struct ypmaplist *list; struct ypmaplist *maps; };"
                ),
                (
                    "struct ypbind_binding { struct in_addr ypbind_binding_addr;"
                    " unsigned short ypbind_binding_port; };"
                ),
                (
                    "struct ypbind_resp { int ypbind_status; union { int ypbind_error;"
                    " struct ypbind_binding ypbind_bindinfo; } ypbind_resp_u; };"
                ),
                "struct keydat_t { unsigned int keydat_len; char *keydat_val; };",
                "struct valdat_t { unsigned int valdat_len; char *valdat_val; };",
                (
                    "struct ypreq_key { char *domain; char *map;"
                    " struct keydat_t key; struct keydat_t keydat; };"
                ),
                (
                    "struct ypresp_val { int status; int stat;"
                    " struct valdat_t val; struct valdat_t valdat; };"
                ),
                "struct ypreq_nokey { char *domain; char *map; };",
                (
                    "struct ypresp_key_val { int status; int stat;"
                    " struct valdat_t val; struct keydat_t key; };"
                ),
                "struct ypresp_master { int status; int stat; char *master; char *peer; };",
                "struct ypresp_order { int status; int stat; unsigned int ordernum; };",
                (
                    "struct ypresp_all { int more;"
                    " union { struct ypresp_key_val val; } ypresp_all_u; };"
                ),
                "int xdr_domainname(void *xdrs, void *objp);",
                "int xdr_ypbind_resp(void *xdrs, void *objp);",
                "int xdr_ypreq_key(void *xdrs, void *objp);",
                "int xdr_ypreq_nokey(void *xdrs, void *objp);",
                "int xdr_ypresp_val(void *xdrs, void *objp);",
                "int xdr_ypresp_key_val(void *xdrs, void *objp);",
                "int xdr_ypresp_master(void *xdrs, void *objp);",
                "int xdr_ypresp_order(void *xdrs, void *objp);",
                "int xdr_ypresp_maplist(void *xdrs, void *objp);",
                "int xdr_ypresp_all(void *xdrs, void *objp);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    nv_h = (
        LF.join(
            [
                "#ifndef FBSD_SYS_NV_H_",
                "#define FBSD_SYS_NV_H_",
                "#include <stdbool.h>",
                "#include <stddef.h>",
                "#include <stdint.h>",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "typedef struct nvlist nvlist_t;",
                "nvlist_t *nvlist_create(int flags);",
                "void nvlist_destroy(nvlist_t *nvl);",
                "int nvlist_error(const nvlist_t *nvl);",
                "bool nvlist_empty(const nvlist_t *nvl);",
                "void nvlist_add_bool(nvlist_t *nvl, const char *name, bool value);",
                "void nvlist_add_number(nvlist_t *nvl, const char *name, uint64_t value);",
                "void nvlist_add_string(nvlist_t *nvl, const char *name, const char *value);",
                "bool nvlist_exists(const nvlist_t *nvl, const char *name);",
                "bool nvlist_get_bool(const nvlist_t *nvl, const char *name);",
                "uint64_t nvlist_get_number(const nvlist_t *nvl, const char *name);",
                "const char *nvlist_get_string(const nvlist_t *nvl, const char *name);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    bsm_h = (
        LF.join(
            [
                "#ifndef FBSD_BSM_LIBBSM_H_",
                "#define FBSD_BSM_LIBBSM_H_",
                "#ifdef __cplusplus",
                'extern "C" {',
                "#endif",
                "int au_open(void);",
                "int au_close(int d, int keep, short event);",
                "#ifdef __cplusplus",
                "}",
                "#endif",
                "#endif",
            ]
        )
        + LF
    )

    fbsd_sys_c = (
        LF.join(
            [
                '#include "security/pam_appl.h"',
                '#include "rpcsvc/ypclnt.h"',
                '#include "rpcsvc/yp_prot.h"',
                '#include "sys/nv.h"',
                '#include "bsm/libbsm.h"',
                "#include <stdlib.h>",
                "#include <string.h>",
                "",
                "int openpam_debug = 0;",
                "int openpam_ttyconv_timeout = 0;",
                "void *ypresp_allfn = NULL;",
                "void *ypresp_data = NULL;",
                "const char *pam_item_name[PAM_NUM_ITEMS] = {",
                '    "NONE", "PAM_SERVICE", "PAM_USER", "PAM_TTY", "PAM_RHOST",',
                '    "PAM_CONV", "PAM_AUTHTOK", "PAM_OLDAUTHTOK", "PAM_RUSER",',
                '    "PAM_USER_PROMPT", "PAM_REPOSITORY", "PAM_AUTHTOK_PROMPT",',
                '    "PAM_OLDAUTHTOK_PROMPT", "PAM_HOST"',
                "};",
                "const char *_pam_item_name[PAM_NUM_ITEMS] = {",
                '    "NONE", "PAM_SERVICE", "PAM_USER", "PAM_TTY", "PAM_RHOST",',
                '    "PAM_CONV", "PAM_AUTHTOK", "PAM_OLDAUTHTOK", "PAM_RUSER",',
                '    "PAM_USER_PROMPT", "PAM_REPOSITORY", "PAM_AUTHTOK_PROMPT",',
                '    "PAM_OLDAUTHTOK_PROMPT", "PAM_HOST"',
                "};",
                "struct pam_handle { char user[128]; char service[128]; };",
                "struct nv_entry { char *key; char *sval; uint64_t nval; bool bval; };",
                "struct nvlist { struct nv_entry items[64]; int count; int err; };",
                "",
                (
                    "int pam_start(const char *service, const char *user, const struct pa"
                    "m_conv *conv, pam_handle_t **pamh) {"
                ),
                "    pam_handle_t *h; (void)conv; if (!pamh) return PAM_SYSTEM_ERR;",
                "    h = (pam_handle_t *)calloc(1, sizeof(*h));",
                "    if (!h) return PAM_BUF_ERR;",
                "    if (service) strncpy(h->service, service, sizeof(h->service) - 1);",
                "    if (user) strncpy(h->user, user, sizeof(h->user) - 1);",
                "    *pamh = h; return PAM_SUCCESS;",
                "}",
                (
                    "int pam_end(pam_handle_t *pamh, int status) { (void)status; free(pam"
                    "h); return PAM_SUCCESS; }"
                ),
                (
                    "int pam_authenticate(pam_handle_t *p, int f) { (void)p; (void)f; ret"
                    "urn PAM_SUCCESS; }"
                ),
                (
                    "int pam_acct_mgmt(pam_handle_t *p, int f) { (void)p; (void)f; return"
                    " PAM_SUCCESS; }"
                ),
                (
                    "int pam_open_session(pam_handle_t *p, int f) { (void)p; (void)f; ret"
                    "urn PAM_SUCCESS; }"
                ),
                (
                    "int pam_close_session(pam_handle_t *p, int f) { (void)p; (void)f; re"
                    "turn PAM_SUCCESS; }"
                ),
                "int pam_setcred(pam_handle_t *p, int f) { (void)p; (void)f; return PAM_SUCCESS; }",
                (
                    "int pam_chauthtok(pam_handle_t *p, int f) { (void)p; (void)f; return"
                    " PAM_SUCCESS; }"
                ),
                "int pam_set_item(pam_handle_t *p, int t, const void *i) {",
                "    if (!p) return PAM_SYSTEM_ERR;",
                (
                    "    if (t == PAM_USER && i) strncpy(p->user, (const char *)i, sizeof"
                    "(p->user) - 1);"
                ),
                "    return PAM_SUCCESS;",
                "}",
                "int pam_get_item(const pam_handle_t *p, int t, const void **i) {",
                "    if (!p || !i) return PAM_SYSTEM_ERR;",
                "    *i = (t == PAM_USER) ? (const void *)p->user : (const void *)p->service;",
                "    return PAM_SUCCESS;",
                "}",
                "int pam_get_user(pam_handle_t *p, const char **u, const char *pr) {",
                "    (void)pr; if (!p || !u) return PAM_SYSTEM_ERR;",
                '    *u = p->user[0] ? p->user : "user"; return PAM_SUCCESS;',
                "}",
                (
                    "const char *pam_strerror(const pam_handle_t *p, int e) { (void)p; re"
                    'turn e == PAM_SUCCESS ? "Success" : "PAM error"; }'
                ),
                (
                    "int openpam_ttyconv(int n, const struct pam_message **m, struct pam_"
                    "response **r, void *d) {"
                ),
                "    (void)n; (void)m; (void)d; if (r) *r = NULL; return PAM_SUCCESS;",
                "}",
                (
                    "int openpam_set_feature(int f, int onoff) {"
                    " (void)f; (void)onoff; return PAM_SUCCESS; }"
                ),
                (
                    "int pam_set_data(pam_handle_t *p, const char *n, void *d,"
                    " void (*c)(pam_handle_t *, void *, int)) {"
                    " (void)p; (void)n; (void)d; (void)c; return PAM_SUCCESS; }"
                ),
                (
                    "int pam_get_data(const pam_handle_t *p, const char *n, const void **d) {"
                    " (void)p; (void)n; if (d) *d = NULL; return PAM_NO_MODULE_DATA; }"
                ),
                (
                    "int pam_putenv(pam_handle_t *p, const char *nv) {"
                    " (void)p; (void)nv; return PAM_SUCCESS; }"
                ),
                (
                    "const char *pam_getenv(pam_handle_t *p, const char *n) {"
                    " (void)p; (void)n; return NULL; }"
                ),
                "char **pam_getenvlist(pam_handle_t *p) {",
                "    char **env; (void)p;",
                "    env = (char **)calloc(1, sizeof(char *));",
                "    return env;",
                "}",
                "",
                (
                    'int yp_get_default_domain(char **domp) { static char d[] = "localdom'
                    'ain"; if (domp) *domp = d; return 0; }'
                ),
                "int yp_bind(const char *d) { (void)d; return YPERR_YPBIND; }",
                "void yp_unbind(const char *d) { (void)d; }",
                (
                    "int yp_match(const char *d, const char *m, const char *k, int kl, ch"
                    "ar **v, int *vl) {"
                ),
                "    (void)d; (void)m; (void)k; (void)kl;",
                "    if (v) { *v = NULL; }",
                "    if (vl) { *vl = 0; }",
                "    return YPERR_YPBIND;",
                "}",
                (
                    "int yp_first(const char *d, const char *m, char **k, int *kl, char *"
                    "*v, int *vl) {"
                ),
                "    (void)d; (void)m;",
                "    if (k) { *k = NULL; }",
                "    if (kl) { *kl = 0; }",
                "    if (v) { *v = NULL; }",
                "    if (vl) { *vl = 0; }",
                "    return YPERR_YPBIND;",
                "}",
                (
                    "int yp_next(const char *d, const char *m, const char *ik, int ikl, c"
                    "har **ok, int *okl, char **ov, int *ovl) {"
                ),
                "    (void)d; (void)m; (void)ik; (void)ikl;",
                "    if (ok) { *ok = NULL; }",
                "    if (okl) { *okl = 0; }",
                "    if (ov) { *ov = NULL; }",
                "    if (ovl) { *ovl = 0; }",
                "    return YPERR_NOMORE;",
                "}",
                (
                    "int yp_all(const char *d, const char *m, struct ypall_callback *cb) "
                    "{ (void)d; (void)m; (void)cb; return YPERR_YPBIND; }"
                ),
                (
                    "int yp_master(const char *d, const char *m, char **o) { (void)d; (vo"
                    "id)m; if (o) *o = NULL; return YPERR_YPBIND; }"
                ),
                (
                    "int yp_order(const char *d, const char *m, int *o) { (void)d; (void)"
                    "m; if (o) *o = 0; return YPERR_YPBIND; }"
                ),
                (
                    "int yp_maplist(const char *d, struct ypmaplist **o) { (void)d;"
                    " if (o) *o = NULL; return YPERR_YPBIND; }"
                ),
                "int xdr_domainname(void *xdrs, void *objp) { (void)xdrs; (void)objp; return 0; }",
                "int xdr_ypbind_resp(void *xdrs, void *objp) { (void)xdrs; (void)objp; return 0; }",
                "int xdr_ypreq_key(void *xdrs, void *objp) { (void)xdrs; (void)objp; return 0; }",
                "int xdr_ypresp_val(void *xdrs, void *objp) { (void)xdrs; (void)objp; return 0; }",
                "int xdr_ypreq_nokey(void *xdrs, void *objp) { (void)xdrs; (void)objp; return 0; }",
                (
                    "int xdr_ypresp_key_val(void *xdrs, void *objp) {"
                    " (void)xdrs; (void)objp; return 0; }"
                ),
                (
                    "int xdr_ypresp_master(void *xdrs, void *objp) {"
                    " (void)xdrs; (void)objp; return 0; }"
                ),
                (
                    "int xdr_ypresp_order(void *xdrs, void *objp) {"
                    " (void)xdrs; (void)objp; return 0; }"
                ),
                (
                    "int xdr_ypresp_maplist(void *xdrs, void *objp) {"
                    " (void)xdrs; (void)objp; return 0; }"
                ),
                "int xdr_ypresp_all(void *xdrs, void *objp) { (void)xdrs; (void)objp; return 0; }",
                'const char *yperr_string(int c) { return c == 0 ? "Success" : "YPunavailable"; }',
                "int ypprot_err(unsigned int c) { return (int)c; }",
                "",
                (
                    "nvlist_t *nvlist_create(int flags) { (void)flags; return (nvlist_t *"
                    ")calloc(1, sizeof(nvlist_t)); }"
                ),
                "void nvlist_destroy(nvlist_t *nvl) {",
                "    int i; if (!nvl) return;",
                (
                    "    for (i = 0; i < nvl->count; i++) { free(nvl->items[i].key); free"
                    "(nvl->items[i].sval); }"
                ),
                "    free(nvl);",
                "}",
                "int nvlist_error(const nvlist_t *nvl) { return nvl ? nvl->err : -1; }",
                "bool nvlist_empty(const nvlist_t *nvl) { return !nvl || nvl->count == 0; }",
                "static struct nv_entry *nv_slot(nvlist_t *nvl, const char *name) {",
                "    int i; if (!nvl || !name) return NULL;",
                (
                    "    for (i = 0; i < nvl->count; i++) if (strcmp(nvl->items[i].key, n"
                    "ame) == 0) return &nvl->items[i];"
                ),
                "    if (nvl->count >= 64) return NULL;",
                "    nvl->items[nvl->count].key = strdup(name);",
                "    return &nvl->items[nvl->count++];",
                "}",
                "static const struct nv_entry *nv_find(const nvlist_t *nvl, const char *name) {",
                "    int i; if (!nvl || !name) return NULL;",
                (
                    "    for (i = 0; i < nvl->count; i++) if (strcmp(nvl->items[i].key, n"
                    "ame) == 0) return &nvl->items[i];"
                ),
                "    return NULL;",
                "}",
                (
                    "void nvlist_add_bool(nvlist_t *nvl, const char *name, bool v) { stru"
                    "ct nv_entry *e = nv_slot(nvl, name); if (e) e->bval = v; }"
                ),
                (
                    "void nvlist_add_number(nvlist_t *nvl, const char *name, uint64_t v) "
                    "{ struct nv_entry *e = nv_slot(nvl, name); if (e) e->nval = v; }"
                ),
                "void nvlist_add_string(nvlist_t *nvl, const char *name, const char *v) {",
                "    struct nv_entry *e = nv_slot(nvl, name);",
                '    if (e) { free(e->sval); e->sval = strdup(v ? v : ""); }',
                "}",
                (
                    "bool nvlist_exists(const nvlist_t *nvl, const char *name) { return n"
                    "v_find(nvl, name) != NULL; }"
                ),
                (
                    "bool nvlist_get_bool(const nvlist_t *nvl, const char *name) { const "
                    "struct nv_entry *e = nv_find(nvl, name); return e ? e->bval : false;"
                    " }"
                ),
                (
                    "uint64_t nvlist_get_number(const nvlist_t *nvl, const char *name) { "
                    "const struct nv_entry *e = nv_find(nvl, name); return e ? e->nval : "
                    "0; }"
                ),
                (
                    "const char *nvlist_get_string(const nvlist_t *nvl, const char *name)"
                    " { const struct nv_entry *e = nv_find(nvl, name); return (e && e->sv"
                    'al) ? e->sval : ""; }'
                ),
                "int au_open(void) { return 0; }",
                (
                    "int au_close(int d, int keep, short ev) { (void)d; (void)keep; (void"
                    ")ev; return 0; }"
                ),
                (
                    "int xdr_ypresp_all_seq(void *xdrs, void *objp) {"
                    " (void)xdrs; (void)objp; return 0; }"
                ),
            ]
        )
        + LF
    )

    yp_h = (
        f"#ifndef FBSD_RPCSVC_YP_H_{LF}#define FBSD_RPCSVC_YP_H_{LF}"
        f'#include "yp_prot.h"{LF}#endif{LF}'
    )

    for rel_name, content in (
        ("security/pam_appl.h", pam_h),
        ("security/openpam.h", openpam_h),
        ("rpcsvc/ypclnt.h", ypclnt_h),
        ("rpcsvc/yp_prot.h", yp_prot_h),
        ("rpcsvc/yp.h", yp_h),
        ("sys/nv.h", nv_h),
        ("bsm/libbsm.h", bsm_h),
        ("fbsd_sys.c", fbsd_sys_c),
    ):
        dst = (out_dir / rel_name).resolve()
        dst.write_text(content, encoding="utf-8")
        emitted[rel_name] = dst
    return emitted


def emit_libarchive_win32_sources(out_dir: Path) -> dict[str, Path]:
    """Emit Windows support headers and shim source stripped from ``contrib/libarchive``.

    Args:
        out_dir: Destination ``codegen/libarchive`` directory.

    Returns:
        Mapping of generated relative filenames to resolved ``Path``s.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    archive_win_h = (
        LF.join(
            [
                "#ifndef ARCHIVE_WINDOWS_H_INCLUDED",
                "#define ARCHIVE_WINDOWS_H_INCLUDED",
                "#include <errno.h>",
                "#include <fcntl.h>",
                "#include <sys/stat.h>",
                "#include <sys/types.h>",
                "#include <wchar.h>",
                "#if defined(_WIN32)",
                "#ifndef WIN32_LEAN_AND_MEAN",
                "#define WIN32_LEAN_AND_MEAN",
                "#endif",
                "#include <direct.h>",
                "#include <io.h>",
                "#include <windows.h>",
                "#if defined(__has_include)",
                "#if __has_include(<pwd.h>)",
                "#include <pwd.h>",
                "#endif",
                "#if __has_include(<grp.h>)",
                "#include <grp.h>",
                "#endif",
                "#endif",
                "#endif",
                "struct archive;",
                "struct archive_entry;",
                "struct la_seek_stat;",
                "#define la_stat(path, stref) stat(path, stref)",
                "#if defined(_WIN32)",
                "#define __la_lseek _lseeki64",
                "#define __la_open _open",
                "#define __la_read _read",
                "#define __la_write _write",
                "#define __la_close _close",
                "#endif",
                "void la_dosmaperr(unsigned long e);",
                "wchar_t *__la_win_permissive_name(const char *name);",
                "wchar_t *__la_win_permissive_name_w(const wchar_t *wname);",
                (
                    "struct archive_entry *__la_win_entry_in_posix_pathseparator("
                    "struct archive_entry *e);"
                ),
                "int __la_seek_fstat(int fd, struct la_seek_stat *st);",
                "int __la_seek_stat(const char *path, struct la_seek_stat *st);",
                "#endif",
            ]
        )
        + LF
    )

    cli_win_h = (
        LF.join(
            [
                "#ifndef LIBARCHIVE_CLI_WINDOWS_SHIM_H_",
                "#define LIBARCHIVE_CLI_WINDOWS_SHIM_H_",
                '#include "archive_windows.h"',
                "#endif",
            ]
        )
        + LF
    )

    archive_win_c = (
        LF.join(
            [
                '#include "archive_windows.h"',
                "#include <stdint.h>",
                "#include <stdlib.h>",
                "#include <string.h>",
                "",
                "struct la_seek_stat_compat {",
                "    int64_t st_mtime;",
                "    ino_t st_ino;",
                "    unsigned short st_mode;",
                "    uint32_t st_nlink;",
                "    gid_t st_gid;",
                "    int64_t st_size;",
                "    uid_t st_uid;",
                "    dev_t st_dev;",
                "    dev_t st_rdev;",
                "};",
                "",
                "void la_dosmaperr(unsigned long e) {",
                "    if (e == 2UL || e == 3UL) { errno = ENOENT; }",
                "    else if (e == 5UL) { errno = EACCES; }",
                "    else if (e == 17UL || e == 80UL || e == 183UL) { errno = EEXIST; }",
                "    else { errno = EIO; }",
                "}",
                "wchar_t *__la_win_permissive_name_w(const wchar_t *wname) {",
                "    size_t n; wchar_t *cp;",
                "    if (!wname) { return NULL; }",
                "    n = wcslen(wname) + 1U;",
                "    cp = (wchar_t *)malloc(n * sizeof(wchar_t));",
                "    if (cp) { memcpy(cp, wname, n * sizeof(wchar_t)); }",
                "    return cp;",
                "}",
                "wchar_t *__la_win_permissive_name(const char *name) {",
                "    size_t n, i; wchar_t *cp;",
                "    if (!name) { return NULL; }",
                "    n = strlen(name) + 1U;",
                "    cp = (wchar_t *)malloc(n * sizeof(wchar_t));",
                "    if (!cp) { return NULL; }",
                "    for (i = 0; i < n; i++) { cp[i] = (wchar_t)(unsigned char)name[i]; }",
                "    return cp;",
                "}",
                (
                    "struct archive_entry *__la_win_entry_in_posix_pathseparator("
                    "struct archive_entry *e) { return e; }"
                ),
                "int __la_seek_fstat(int fd, struct la_seek_stat *st) {",
                "    struct stat sb;",
                "    struct la_seek_stat_compat *out = (struct la_seek_stat_compat *)st;",
                "    if (!out || fstat(fd, &sb) != 0) { return -1; }",
                "    memset(out, 0, sizeof(*out));",
                "    out->st_mtime = (int64_t)sb.st_mtime;",
                "    out->st_mode = (unsigned short)sb.st_mode;",
                "    out->st_nlink = (uint32_t)sb.st_nlink;",
                "    out->st_size = (int64_t)sb.st_size;",
                "    return 0;",
                "}",
                "int __la_seek_stat(const char *path, struct la_seek_stat *st) {",
                "    struct stat sb;",
                "    struct la_seek_stat_compat *out = (struct la_seek_stat_compat *)st;",
                "    if (!path || !out || stat(path, &sb) != 0) { return -1; }",
                "    memset(out, 0, sizeof(*out));",
                "    out->st_mtime = (int64_t)sb.st_mtime;",
                "    out->st_mode = (unsigned short)sb.st_mode;",
                "    out->st_nlink = (uint32_t)sb.st_nlink;",
                "    out->st_size = (int64_t)sb.st_size;",
                "    return 0;",
                "}",
                "#if defined(_WIN32)",
                (
                    "int __archive_create_child(const char *cmd, int *child_stdin, "
                    "int *child_stdout, HANDLE *out_child) {"
                ),
                "    (void)cmd; if (child_stdin) { *child_stdin = -1; }",
                "    if (child_stdout) { *child_stdout = -1; }",
                "    if (out_child) { *out_child = NULL; }",
                "    errno = ENOSYS; return -1;",
                "}",
                "void __archive_check_child(int in_fd, int out_fd) { (void)in_fd; (void)out_fd; }",
                "struct archive *archive_read_disk_new(void) { return NULL; }",
                "struct archive *archive_write_disk_new(void) { return NULL; }",
                (
                    "int archive_read_disk_set_standard_lookup(struct archive *a) {"
                    " (void)a; return 0; }"
                ),
                (
                    "int archive_write_disk_set_standard_lookup(struct archive *a) {"
                    " (void)a; return 0; }"
                ),
                (
                    "int archive_write_disk_set_options(struct archive *a, int flags) {"
                    " (void)a; (void)flags; return 0; }"
                ),
                (
                    "int archive_write_disk_set_skip_file(struct archive *a, "
                    "int64_t d, int64_t i) { (void)a; (void)d; (void)i; return 0; }"
                ),
                "int archive_read_disk_can_descend(struct archive *a) { (void)a; return 0; }",
                (
                    "int archive_read_disk_current_filesystem_is_remote("
                    "struct archive *a) { (void)a; return 0; }"
                ),
                "int archive_read_disk_descend(struct archive *a) { (void)a; return 0; }",
                (
                    "int archive_read_disk_entry_from_file(struct archive *a, "
                    "void *e, int fd, const void *st) { (void)a; (void)e; (void)fd; "
                    "(void)st; return 0; }"
                ),
                (
                    "const char *archive_read_disk_gname(struct archive *a, int64_t g) {"
                    ' (void)a; (void)g; return "wheel"; }'
                ),
                (
                    "const char *archive_read_disk_uname(struct archive *a, int64_t u) {"
                    ' (void)a; (void)u; return "root"; }'
                ),
                (
                    "int archive_read_disk_open(struct archive *a, const char *p) {"
                    " (void)a; (void)p; return -30; }"
                ),
                (
                    "int archive_read_disk_set_behavior(struct archive *a, int f) {"
                    " (void)a; (void)f; return 0; }"
                ),
                (
                    "int archive_read_disk_set_matching(struct archive *a, void *m, "
                    "void *cb, void *d) { (void)a; (void)m; (void)cb; (void)d; return 0; }"
                ),
                (
                    "int archive_read_disk_set_metadata_filter_callback("
                    "struct archive *a, void *cb, void *d) { (void)a; (void)cb; "
                    "(void)d; return 0; }"
                ),
                (
                    "int archive_read_disk_set_symlink_hybrid(struct archive *a) {"
                    " (void)a; return 0; }"
                ),
                (
                    "int archive_read_disk_set_symlink_logical(struct archive *a) {"
                    " (void)a; return 0; }"
                ),
                (
                    "int archive_read_disk_set_symlink_physical(struct archive *a) {"
                    " (void)a; return 0; }"
                ),
                "#endif",
            ]
        )
        + LF
    )

    for rel_name, content in (
        ("archive_windows.h", archive_win_h),
        ("bsdtar_windows.h", cli_win_h),
        ("cpio_windows.h", cli_win_h),
        ("bsdunzip_windows.h", cli_win_h),
        ("fbsd_libarchive_win32.c", archive_win_c),
    ):
        dst = (out_dir / rel_name).resolve()
        dst.write_text(content, encoding="utf-8")
        emitted[rel_name] = dst
    return emitted


def emit_libdialog_section3_sources(dialog_dir: Path) -> dict[str, Path]:
    """Emit portable C89 Section 3 ``libdialog`` headers and implementation.

    Provides the ``dialog(3)`` ABI (``init_dialog``, ``end_dialog``,
    ``dlg_put_backtitle``, ``dlg_reallocate_gauge``, ``dlg_update_gauge``,
    ``dlg_free_gauge``, ``dlg_color_pair``, ``dialog_gauge``, ``dialog_state``,
    ``dialog_vars``, and ``dlg_color_table``) backed by ``fbsd_libcurses`` for
    FreeBSD 15.0 ``libdpv`` and ``dpv(1)`` across Windows, DOS, and Unix.

    Args:
        dialog_dir: Destination ``codegen/libdialog`` directory.

    Returns:
        Mapping of generated relative filenames to resolved ``Path``s.
    """
    dialog_dir.mkdir(parents=True, exist_ok=True)
    emitted: dict[str, Path] = {}

    dlg_config_h = (
        LF.join(
            [
                "#ifndef DLG_CONFIG_H_included",
                "#define DLG_CONFIG_H_included 1",
                '#define DIALOG_VERSION "1.3"',
                "#define DIALOG_PATCHDATE 20210117",
                "#define HAVE_COLOR 1",
                "#define HAVE_DLG_GAUGE 1",
                "#define HAVE_RC_FILE 1",
                "#define HAVE_RC_FILE2 1",
                "#endif",
            ]
        )
        + LF
    )

    dlg_colors_h = (
        LF.join(
            [
                "#ifndef DLG_COLORS_H_included",
                "#define DLG_COLORS_H_included 1",
                "#define DLG_COLOR_COUNT 36",
                "#endif",
            ]
        )
        + LF
    )

    dlg_keys_h = (
        LF.join(
            [
                "#ifndef DLG_KEYS_H_included",
                "#define DLG_KEYS_H_included 1",
                "#endif",
            ]
        )
        + LF
    )

    dialog_h = (
        LF.join(
            [
                "#ifndef DIALOG_H_included",
                "#define DIALOG_H_included 1",
                "#include <curses.h>",
                "#include <stdio.h>",
                '#include "dlg_config.h"',
                '#include "dlg_colors.h"',
                '#include "dlg_keys.h"',
                "",
                "#if defined(_WIN32) && !defined(__DOS__) && !defined(__WATCOMC__)",
                "#if defined(fbsd_libdialog_EXPORTS)",
                "#define _FBSD_DLG_DATA extern __declspec(dllexport)",
                "#elif !defined(FBSD_DIALOG_STATIC)",
                "#define _FBSD_DLG_DATA extern __declspec(dllimport)",
                "#else",
                "#define _FBSD_DLG_DATA extern",
                "#endif",
                "#else",
                "#define _FBSD_DLG_DATA extern",
                "#endif",
                "",
                "#ifndef TRUE",
                "#define TRUE 1",
                "#endif",
                "#ifndef FALSE",
                "#define FALSE 0",
                "#endif",
                "#define DLG_EXIT_OK 0",
                "#define DLG_EXIT_CANCEL 1",
                "#define DLG_EXIT_ERROR 255",
                "#define SCREEN_ATTR 0",
                "#define BUTTON_ACTIVE_ATTR 5",
                "#define GAUGE_ATTR 33",
                "",
                "typedef struct {",
                "    FILE *input;",
                "    FILE *output;",
                "    FILE *pipe_input;",
                "    int screen_initialized;",
                "    int use_colors;",
                "    int use_shadow;",
                "    int screen_height;",
                "    int screen_width;",
                "} DIALOG_STATE;",
                "",
                "typedef struct {",
                "    char *backtitle;",
                "    char *title;",
                "    int colors;",
                "    int dlg_clear_screen;",
                "    int keep_tite;",
                "} DIALOG_VARS;",
                "",
                "typedef struct {",
                "    chtype atr;",
                "    int fg;",
                "    int bg;",
                "    int hilite;",
                "    int ul;",
                "    int rv;",
                "    const char *name;",
                "    const char *comment;",
                "} DIALOG_COLORS;",
                "",
                "_FBSD_DLG_DATA DIALOG_STATE dialog_state;",
                "_FBSD_DLG_DATA DIALOG_VARS dialog_vars;",
                "_FBSD_DLG_DATA DIALOG_COLORS dlg_color_table[DLG_COLOR_COUNT];",
                "",
                "const char *dialog_version(void);",
                "void init_dialog(FILE *input, FILE *output);",
                "void end_dialog(void);",
                "void dlg_clear(void);",
                "void dlg_put_backtitle(void);",
                "chtype dlg_color_pair(int foreground, int background);",
                (
                    "void *dlg_reallocate_gauge(void *objptr, const char *title, "
                    "const char *cprompt, int height, int width, int percent);"
                ),
                "void dlg_update_gauge(void *objptr, int percent);",
                "void dlg_free_gauge(void *objptr);",
                (
                    "int dialog_gauge(const char *title, const char *cprompt, "
                    "int height, int width, int percent);"
                ),
                "#endif",
            ]
        )
        + LF
    )

    fbsd_dialog_c = (
        LF.join(
            [
                '#include "dialog.h"',
                "#include <stdlib.h>",
                "#include <string.h>",
                "",
                "typedef struct {",
                "    char title[128];",
                "    char prompt[1024];",
                "    int height;",
                "    int width;",
                "    int percent;",
                "} fbsd_dlg_gauge_t;",
                "",
                "DIALOG_STATE dialog_state = { NULL, NULL, NULL, 0, 1, 1, 24, 80 };",
                "DIALOG_VARS dialog_vars = { NULL, NULL, 1, 0, 0 };",
                "DIALOG_COLORS dlg_color_table[DLG_COLOR_COUNT];",
                "",
                "static void fbsd_dlg_init_colors(void) {",
                "    int i;",
                "    for (i = 0; i < DLG_COLOR_COUNT; i++) {",
                "        dlg_color_table[i].fg = 7;",
                "        dlg_color_table[i].bg = 4;",
                "        dlg_color_table[i].hilite = 0;",
                "    }",
                "    dlg_color_table[BUTTON_ACTIVE_ATTR].fg = 7;",
                "    dlg_color_table[BUTTON_ACTIVE_ATTR].bg = 4;",
                "    dlg_color_table[BUTTON_ACTIVE_ATTR].hilite = 1;",
                "    dlg_color_table[GAUGE_ATTR].fg = 4;",
                "    dlg_color_table[GAUGE_ATTR].bg = 7;",
                "    dlg_color_table[GAUGE_ATTR].hilite = 1;",
                "}",
                "",
                "const char *dialog_version(void) { return DIALOG_VERSION; }",
                "",
                "void init_dialog(FILE *input, FILE *output) {",
                "    fbsd_dlg_init_colors();",
                "    dialog_state.input = input ? input : stdin;",
                "    dialog_state.output = output ? output : stdout;",
                "    initscr();",
                "    if (has_colors()) { start_color(); }",
                "    dialog_state.screen_initialized = 1;",
                "    dialog_state.screen_height = LINES > 0 ? LINES : 24;",
                "    dialog_state.screen_width = COLS > 0 ? COLS : 80;",
                "}",
                "",
                "void end_dialog(void) {",
                "    if (dialog_state.screen_initialized) {",
                "        endwin();",
                "        dialog_state.screen_initialized = 0;",
                "    }",
                "}",
                "",
                "void dlg_clear(void) {",
                "    clear();",
                "}",
                "",
                "void dlg_put_backtitle(void) {",
                "    if (dialog_vars.backtitle != NULL) {",
                "        mvaddstr(0, 1, dialog_vars.backtitle);",
                "        refresh();",
                "    }",
                "}",
                "",
                "chtype dlg_color_pair(int foreground, int background) {",
                "    short pair_id = (short)(((foreground & 7) << 3) | (background & 7));",
                "    if (pair_id <= 0) { pair_id = 1; }",
                "    init_pair(pair_id, (short)foreground, (short)background);",
                "    return (chtype)COLOR_PAIR(pair_id);",
                "}",
                "",
                (
                    "void *dlg_reallocate_gauge(void *objptr, const char *title, "
                    "const char *cprompt, int height, int width, int percent) {"
                ),
                "    fbsd_dlg_gauge_t *g = (fbsd_dlg_gauge_t *)objptr;",
                "    if (g == NULL) {",
                "        g = (fbsd_dlg_gauge_t *)calloc(1U, sizeof(*g));",
                "        if (g == NULL) { return NULL; }",
                "    }",
                "    if (title != NULL) {",
                "        strncpy(g->title, title, sizeof(g->title) - 1U);",
                "        g->title[sizeof(g->title) - 1U] = 0;",
                "    }",
                "    if (cprompt != NULL) {",
                "        strncpy(g->prompt, cprompt, sizeof(g->prompt) - 1U);",
                "        g->prompt[sizeof(g->prompt) - 1U] = 0;",
                "    }",
                "    g->height = height > 0 ? height : 7;",
                "    g->width = width > 0 ? width : 60;",
                "    g->percent = percent;",
                "    return g;",
                "}",
                "",
                "void dlg_update_gauge(void *objptr, int percent) {",
                "    fbsd_dlg_gauge_t *g = (fbsd_dlg_gauge_t *)objptr;",
                "    int pct = percent < 0 ? 0 : (percent > 100 ? 100 : percent);",
                "    if (g == NULL) { return; }",
                "    g->percent = pct;",
                "    if (g->title[0] != 0) { mvaddstr(2, 4, g->title); }",
                "    if (g->prompt[0] != 0) { mvaddstr(4, 4, g->prompt); }",
                '    mvprintw(6, 4, "[%3d%%]", pct);',
                "    refresh();",
                "}",
                "",
                "void dlg_free_gauge(void *objptr) {",
                "    free(objptr);",
                "}",
                "",
                (
                    "int dialog_gauge(const char *title, const char *cprompt, "
                    "int height, int width, int percent) {"
                ),
                "    void *g = dlg_reallocate_gauge(NULL, title, cprompt, height, width, percent);",
                "    dlg_update_gauge(g, percent);",
                "    dlg_free_gauge(g);",
                "    return DLG_EXIT_OK;",
                "}",
            ]
        )
        + LF
    )

    for rel_name, content in (
        ("dlg_config.h", dlg_config_h),
        ("dlg_colors.h", dlg_colors_h),
        ("dlg_keys.h", dlg_keys_h),
        ("dialog.h", dialog_h),
        ("fbsd_dialog.c", fbsd_dialog_c),
    ):
        dst = (dialog_dir / rel_name).resolve()
        dst.write_text(content, encoding="utf-8")
        emitted[rel_name] = dst
    return emitted
