#!/bin/bash

grep Mean *.log | sed -n 's/testlog_\([^_]*\)[^:]*[^0-9]*\([0-9.]*\)ms/\1,\2/g; p' | sort -n > mean.csv
grep Longest *.log | sed -n 's/testlog_\([^_]*\)[^:]*[^0-9]*\([0-9.]*\)ms/\1,\2/g; p' | sort -n > longest.csv
csvjoin --columns 1 mean.csv longest.csv | sort -n -t, -k1,1 > logresults.csv
gnuplot <<- EOF
set terminal pngcairo nocrop enhanced font "verdana,10" size 1024,768
set output 'plot.png'
unset border
set boxwidth 0.1
set style fill solid 1.00

#set terminal svg size 410,250 fname 'Verdana, Helvetica, Arial, sans-serif' fsize '9' rounded dashed
#set output 'plot.svg'

# remove border on top and right and set color to gray
set style line 11 lc rgb '#808080' lt 1
set border 3 back ls 11
set tics nomirror

# define grid
set style line 12 lc rgb '#808080' lt 0 lw 1
set grid back ls 12

# color definitions
set style line 1 lc rgb '#8b1a0e' pt 1 ps 1 lt 1 lw 2 # --- red
set style line 2 lc rgb '#5e9c36' pt 6 ps 1 lt 1 lw 2 # --- green

set datafile separator ','
set ylabel 'Propagation time (ms)'
set xlabel 'Number of webthings'
plot 'logresults.csv' using 1:2 t 'mean' w lp ls 1, '' using 1:3 t 'longest' w lp ls 2
EOF
