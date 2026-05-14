CFLAGS  := -O2 -Wall -Wextra -I/usr/local/include
LDFLAGS := -L/usr/local/lib -Wl,-rpath,/usr/local/lib
LDLIBS  := -lethercat -lm -lrt

csp_smoke: csp_smoke.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS) $(LDLIBS)

clean:
	rm -f csp_smoke

.PHONY: clean
