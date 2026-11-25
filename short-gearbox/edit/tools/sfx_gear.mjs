// Звуки для ролика о коробках передач — синтез ffmpeg → public/*.wav
import fs from "node:fs";
import { execFileSync } from "node:child_process";
fs.mkdirSync("public", { recursive: true });
const st = "aformat=channel_layouts=stereo:sample_rates=48000";
const ff = (args, out) => { execFileSync("ffmpeg", ["-v", "error", "-y", ...args, `public/${out}.wav`]); console.log("✅", out); };
const ev = (expr, d, af, out) => ff(["-f", "lavfi", "-i", `aevalsrc='${expr}':s=48000:d=${d}`, "-af", `${af},${st}`], out);
// дождь (эмбиент)
ff(["-f", "lavfi", "-i", "anoisesrc=d=8:c=pink:a=0.5:r=48000", "-f", "lavfi", "-i", "anoisesrc=d=8:c=white:a=0.15:r=48000", "-filter_complex",
  `[0]lowpass=f=2500,highpass=f=300[a];[1]highpass=f=6000[b];[a][b]amix=inputs=2:normalize=0,afade=t=in:d=0.4,afade=t=out:st=7.4:d=0.6,${st}`], "amb_rain");
// рывок машины: глухой удар + скрип
ev("0.9*sin(2*PI*55*t)*exp(-9*t)+0.25*sin(2*PI*(900-500*t)*t)*exp(-14*t)", 0.6, "lowpass=f=1500", "sfx_jerk");
// гудок сзади
ev("0.35*(sin(2*PI*392*t)+sin(2*PI*494*t))*lt(t\,0.55)", 0.7, "lowpass=f=2500,afade=t=in:d=0.02,afade=t=out:st=0.45:d=0.2", "sfx_horn");
// механический щелчок
ff(["-f", "lavfi", "-i", "anoisesrc=d=0.08:c=white:a=0.9:r=48000", "-af", `highpass=f=1800,afade=t=out:st=0.004:d=0.07:curve=exp,${st}`], "sfx_click");
// пуск мотора и холостой ход
ev("0.6*sin(2*PI*(30+25*min(t\,0.6))*t)*(0.6+0.4*sin(2*PI*14*t))*min(1\,t*4)", 2.5, "lowpass=f=600,afade=t=out:st=1.8:d=0.7", "sfx_engine");
// гул рентгена
ev("0.5*sin(2*PI*55*t)+0.2*sin(2*PI*110.5*t)", 5, "lowpass=f=300,afade=t=in:d=0.6,afade=t=out:st=4:d=1", "sfx_hum");
// шестерни: зубцовая частота + металлический звон
ev("0.35*sin(2*PI*180*t)*(0.5+0.5*sin(2*PI*33*t))+0.12*sin(2*PI*1320*t)*(0.5+0.5*sin(2*PI*33*t))", 5, "highpass=f=80,afade=t=in:d=0.3,afade=t=out:st=4:d=1", "sfx_gears");
// переключение рычага: клац-клац
ff(["-f", "lavfi", "-i", "anoisesrc=d=0.35:c=white:a=0.9:r=48000", "-af",
  `highpass=f=1200,volume='if(lt(t,0.03),1,if(between(t,0.18,0.21),0.9,0))':eval=frame,lowpass=f=7000,${st}`], "sfx_shift");
// жидкость в гидротрансформаторе
ff(["-f", "lavfi", "-i", "anoisesrc=d=6:c=brown:a=0.7:r=48000", "-af", `bandpass=f=350:w=300,tremolo=f=5:d=0.5,afade=t=in:d=0.5,afade=t=out:st=5:d=1,${st}`], "sfx_fluid");
// вариатор: ровный нарастающий вой без ступеней
ev("0.35*sin(2*PI*(140*t+40*t*t/2))+0.1*sin(2*PI*(420*t+120*t*t/2))", 6, "lowpass=f=1800,afade=t=in:d=0.6,afade=t=out:st=5:d=1", "sfx_whir");
// электронный писк
ev("0.3*sin(2*PI*2000*t)*(lt(t\,0.07)+between(t\,0.12\,0.19))", 0.25, "afade=t=out:st=0.2:d=0.05", "sfx_beep");
// рёв разгона
ev("0.55*sin(2*PI*(60*t+90*t*t/2))*(0.7+0.3*sin(2*PI*25*t))", 1.6, "lowpass=f=900,afade=t=in:d=0.05,afade=t=out:st=1.1:d=0.5", "sfx_rev");
