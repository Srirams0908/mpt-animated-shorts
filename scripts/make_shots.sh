#!/bin/bash
# shot name | image | duration | zoom | x_from | x_to (fraction of pan range) | y_from | y_to (fraction)
shot() {
  n=$1; img=$2; d=$3; z=$4; xa=$5; xb=$6; ya=$7; yb=$8
  H=$(python3 -c "print(int(1920*$z))")
  ffmpeg -y -loglevel error -loop 1 -framerate 30 -t $d -i $img -vf \
"scale=-2:$H:flags=lanczos,crop=1080:1920:x='(iw-1080)*($xa+($xb-$xa)*t/$d)':y='(ih-1920)*($ya+($yb-$ya)*t/$d)',eq=saturation=1.12:contrast=1.04,vignette=PI/6,noise=alls=3:allf=t,format=yuv420p" \
    -r 30 -c:v libx264 -crf 17 -preset medium shot_$n.mp4
}
shot 1 s1.png 5.6 1.10 0.00 0.30 0.00 0.25
shot 2 s2.png 2.4 1.10 0.10 0.55 0.30 0.30
shot 3 s3.png 2.3 1.10 0.00 0.35 0.50 0.50
shot 4 s3.png 4.4 1.10 1.00 0.60 0.50 0.50
shot 5 s2.png 2.7 1.10 0.55 0.90 0.00 0.00
shot 6 s3.png 4.6 1.10 0.40 0.62 0.50 0.35
