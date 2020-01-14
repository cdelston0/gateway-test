#!/bin/bash

# Aggregate log results from subdirs *_test_logs into two plots, one of the means of all machines and one of longest of all machines

HEAD="webthings"
PLOTCMD=""
PLOTNEXT=2
for file in *_test_logs; do
    MACHINE=`echo ${file} | cut -d'_' -f1`
    HEAD+=",${MACHINE}"
    PLOTCMD+=", '' using 1:${PLOTNEXT} with lines"
    PLOTNEXT=$((PLOTNEXT+1))
    grep Mean ${file}/*.log | sed -n "s/${file}\/testlog_\([^_]*\)[^:]*[^0-9]*\([0-9.]*\)ms/\1,\2/g; p" | sort -n > ${MACHINE}_mean.csv
    grep Longest ${file}/*.log | sed -n "s/${file}\/testlog_\([^_]*\)[^:]*[^0-9]*\([0-9.]*\)ms/\1,\2/g; p" | sort -n > ${MACHINE}_longest.csv
done

PLOTCMD=`echo ${PLOTCMD} | cut -c6-`

echo "${HEAD}" > logresults_mean_all.csv
echo "${HEAD}" > logresults_longest_all.csv

csvjoin --columns 1 *_mean.csv | sort -n -t, -k1,1 >> logresults_mean_all.csv
csvjoin --columns 1 *_longest.csv | sort -n -t, -k1,1 >> logresults_longest_all.csv

read -r -d '' PLOT_COMMON << EOM
set terminal pngcairo nocrop enhanced font "verdana,10" size 1024,768
unset border
set boxwidth 0.1
set style fill solid 1.00

#set terminal svg size 410,250 fname 'Verdana, Helvetica, Arial, sans-serif' fsize '9' rounded dashed

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

set key left top

set datafile separator ','
set ylabel 'Propagation time (ms)'
set xlabel 'Number of webthings'
set key autotitle columnhead
EOM

gnuplot <<- EOF
set output 'plot_mean.png'
${PLOT_COMMON}
plot 'logresults_mean_all.csv' ${PLOTCMD}
EOF

gnuplot <<- EOF
set output 'plot_longest.png'
${PLOT_COMMON}
plot 'logresults_longest_all.csv' ${PLOTCMD}
EOF
