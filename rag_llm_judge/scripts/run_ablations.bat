@echo off
echo ============================================================
echo Running Ablation Experiments
echo ============================================================

echo.
echo [1/9] Learning Rate: 1e-5
python scripts/train.py --data_dir baseline --quantize --use_lora --learning_rate 1e-5 --output_dir outputs/lr_1e5 --num_epochs 3

echo.
echo [2/9] Learning Rate: 2e-5
python scripts/train.py --data_dir baseline --quantize --use_lora --learning_rate 2e-5 --output_dir outputs/lr_2e5 --num_epochs 3

echo.
echo [3/9] Learning Rate: 5e-5
python scripts/train.py --data_dir baseline --quantize --use_lora --learning_rate 5e-5 --output_dir outputs/lr_5e5 --num_epochs 3

echo.
echo [4/9] LoRA Rank: 8
python scripts/train.py --data_dir baseline --quantize --use_lora --lora_r 8 --output_dir outputs/lora_r8 --num_epochs 3

echo.
echo [5/9] LoRA Rank: 16
python scripts/train.py --data_dir baseline --quantize --use_lora --lora_r 16 --output_dir outputs/lora_r16 --num_epochs 3

echo.
echo [6/9] LoRA Rank: 32
python scripts/train.py --data_dir baseline --quantize --use_lora --lora_r 32 --output_dir outputs/lora_r32 --num_epochs 3

echo.
echo [7/9] Epochs: 1
python scripts/train.py --data_dir baseline --quantize --use_lora --num_epochs 1 --output_dir outputs/ep_1

echo.
echo [8/9] Epochs: 3
python scripts/train.py --data_dir baseline --quantize --use_lora --num_epochs 3 --output_dir outputs/ep_3

echo.
echo [9/9] Epochs: 5
python scripts/train.py --data_dir baseline --quantize --use_lora --num_epochs 5 --output_dir outputs/ep_5

echo.
echo ============================================================
echo All ablations complete!
echo ============================================================
echo.
echo Now run: python scripts/analyze_results.py --results_dir outputs/
pause