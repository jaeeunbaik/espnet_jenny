import os
import pypinyin
import argparse
import re
import shutil
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Define folders to be removed
FOLDERS_TO_REMOVE = [
    '其它语音 - Others',
    '带变量语音 - Placeholder',
    '战斗语音 - Battle',
    '#Unknown'
]

# Supported audio formats
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.flac'}

def has_chinese(text: str) -> bool:
    """Check if the text contains Chinese characters"""
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def clean_name(text: str) -> str:
    # Only keep letters, numbers and spaces
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    # Remove extra spaces and strip
    cleaned = ' '.join(cleaned.split())
    return cleaned

def convert_to_pinyin(text: str) -> str:
    try:
        pinyin_list = pypinyin.lazy_pinyin(text, strict=False)
        # Join and clean the pinyin result
        pinyin = ''.join(word.capitalize() for word in pinyin_list)
        return clean_name(pinyin)
    except Exception as e:
        print(f"Error converting pinyin for '{text}': {str(e)}")
        return clean_name(text)

def safe_remove_folder(folder_path: str, dry_run: bool = False) -> bool:
    try:
        if dry_run:
            print(f"[Preview] Would remove folder: {folder_path}")
            return True
            
        shutil.rmtree(folder_path)
        print(f"Successfully removed folder: {folder_path}")
        return True
        
    except PermissionError:
        print(f"Permission error when removing: {folder_path}")
    except Exception as e:
        print(f"Error removing folder {folder_path}: {str(e)}")
    return False

def safe_rename(old_path: str, new_path: str) -> bool:
    try:
        if old_path == new_path:
            return True
            
        base_path = new_path
        counter = 1
        while os.path.exists(new_path):
            name, ext = os.path.splitext(base_path)
            new_path = f"{name}_{counter}{ext}"
            counter += 1
        
        os.rename(old_path, new_path)
        print(f"Renamed successfully: {os.path.basename(old_path)} -> {os.path.basename(new_path)}")
        return True
        
    except PermissionError:
        print(f"Permission error: {old_path}")
    except OSError as e:
        print(f"Failed to rename {old_path}: {str(e)}")
    except Exception as e:
        print(f"Unknown error for {old_path}: {str(e)}")
    return False

def get_audio_duration(file_path: str) -> float:
    """Get duration of audio file in seconds"""
    try:
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0  # Convert milliseconds to seconds
    except Exception as e:
        print(f"Error getting duration for {file_path}: {str(e)}")
        return 0.0

def convert_audio_format(file_path: str, dry_run: bool = False) -> tuple[str, bool]:
    """Convert audio to mono 44.1kHz WAV format"""
    try:
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return file_path, False

        if file_path.lower().endswith('.wav'):
            try:
                import soundfile as sf
                data, sample_rate = sf.read(file_path)
                
                needs_conversion = False
                
                if len(data.shape) > 1 and data.shape[1] > 1:
                    needs_conversion = True
                    print(f"File needs mono conversion: {os.path.basename(file_path)}")
                
                if sample_rate != 44100:
                    needs_conversion = True
                    print(f"File needs resampling: {os.path.basename(file_path)} (current: {sample_rate}Hz)")
                
                if not needs_conversion:
                    print(f"File already in correct format: {os.path.basename(file_path)}")
                    return file_path, False
                    
                if dry_run:
                    print(f"[Preview] Would convert: {file_path}")
                    print(f"         (current: channels={data.shape[1] if len(data.shape)>1 else 1}, "
                          f"sample rate={sample_rate}Hz)")
                    return file_path, True
                
                if len(data.shape) > 1 and data.shape[1] > 1:
                    data = data.mean(axis=1)
                
                if sample_rate != 44100:
                    from scipy import signal
                    new_length = int(len(data) * 44100 / sample_rate)
                    data = signal.resample(data, new_length)
                
                sf.write(file_path, data, 44100)
                print(f"Converted: {os.path.basename(file_path)}")
                return file_path, True
                
            except Exception as e:
                print(f"Error processing WAV file with soundfile: {str(e)}")
                pass
        
        audio = AudioSegment.from_file(file_path)
        
        if audio.channels > 1:
            audio = audio.set_channels(1)
            print(f"Converting to mono: {os.path.basename(file_path)}")
            
        if audio.frame_rate != 44100:
            audio = audio.set_frame_rate(44100)
            print(f"Resampling: {os.path.basename(file_path)} -> 44100Hz")
            
        new_path = str(Path(file_path).with_suffix('.wav'))
        
        if (file_path == new_path and 
            audio.channels == 1 and 
            audio.frame_rate == 44100):
            return file_path, False
            
        if dry_run:
            print(f"[Preview] Would convert: {file_path} -> {new_path}")
            print(f"         (mono: {audio.channels == 1}, "
                  f"sample rate: {audio.frame_rate}Hz)")
            return new_path, True
            
        audio.export(new_path, format='wav')
        
        if file_path != new_path:
            os.remove(file_path)
            
        print(f"Converted: {os.path.basename(file_path)} -> "
              f"{os.path.basename(new_path)}")
        return new_path, True
        
    except Exception as e:
        print(f"Error converting {file_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return file_path, False


def process_audio_file(args) -> tuple:
    """Process a single audio file and return if it should be removed"""
    file_path, dry_run = args
    
    file_path, _ = convert_audio_format(file_path, dry_run)
    
    duration = get_audio_duration(file_path)
    if duration < 1.0:
        if dry_run:
            print(f"[Preview] Would remove short audio: {file_path} "
                  f"(duration: {duration:.2f}s)")
        else:
            try:
                os.remove(file_path)
                os.remove(file_path.replace('.wav', '.lab'))
                print(f"Removed short audio: {file_path} "
                      f"(duration: {duration:.2f}s)")
            except Exception as e:
                print(f"Error removing {file_path}: {str(e)}")
        return file_path, True
    return file_path, False

def remove_short_audio_files(target_folder: str, dry_run: bool = False) -> None:
    """Remove audio files shorter than 1 second"""
    print("\n=== Removing audio files shorter than 1 second ===")
    
    audio_files = []
    for root, _, files in os.walk(target_folder):
        for file in files:
            if Path(file).suffix.lower() in AUDIO_EXTENSIONS:
                audio_files.append((os.path.join(root, file), dry_run))
    
    if not audio_files:
        print("No audio files found")
        return
        
    print(f"Processing {len(audio_files)} audio files...")
    
    # Process files in parallel
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        results = list(executor.map(process_audio_file, audio_files))
    
    removed_count = sum(1 for _, removed in results if removed)
    print(f"\nProcessed {len(audio_files)} files, removed {removed_count} short audio files")

def remove_specific_folders(target_folder: str, dry_run: bool = False) -> None:
    """Remove specified folders before renaming"""
    try:
        for root, dirs, _ in os.walk(target_folder, topdown=False):
            for dir_name in dirs:
                if dir_name in FOLDERS_TO_REMOVE:
                    folder_path = os.path.join(root, dir_name)
                    safe_remove_folder(folder_path, dry_run)
    except Exception as e:
        print(f"Error during folder removal: {str(e)}")

def rename_speaker_folders(target_folder: str, dry_run: bool = False) -> None:
    """Remove trailing '{num}', '-{num}', or '_{num}' from speaker folder names and merge contents if necessary"""
    print("\n=== Removing trailing '{num}', '-{num}', or '_{num}' from speaker folders ===")
    try:
        pattern = re.compile(r'[_-]?(\d+)$')
        for root, dirs, _ in os.walk(target_folder, topdown=False):
            for dir_name in dirs:
                match = pattern.search(dir_name)
                if match:
                    old_path = os.path.join(root, dir_name)
                    new_name = dir_name[:match.start()]
                    new_path = os.path.join(root, new_name)
                    
                    if dry_run:
                        print(f"[Preview] Will rename: {dir_name} -> {new_name}")
                    else:
                        if os.path.exists(new_path):
                            # Merge contents
                            for item in os.listdir(old_path):
                                shutil.move(os.path.join(old_path, item), new_path)
                            shutil.rmtree(old_path)
                            print(f"Merged and removed folder: {old_path} -> {new_path}")
                        else:
                            safe_rename(old_path, new_path)
                        
    except Exception as e:
        print(f"Error processing speaker folders: {str(e)}")

def rename_folders_to_pinyin(target_folder: str, dry_run: bool = False) -> None:
    try:
        if not os.path.exists(target_folder):
            print(f"Target folder does not exist: {target_folder}")
            return
        
        print("\n=== Removing specified folders ===")
        remove_specific_folders(target_folder, dry_run)
        
        print("\n=== Converting folder names to Pinyin ===")
        for root, dirs, _ in os.walk(target_folder, topdown=False):
            for dir_name in dirs:
                if has_chinese(dir_name):
                    old_path = os.path.join(root, dir_name)
                    new_name = convert_to_pinyin(dir_name)
                    
                    if not new_name:
                        print(f"Skipping {dir_name}: name would be empty after cleaning")
                        continue
                        
                    new_path = os.path.join(root, new_name)
                    
                    if dry_run:
                        print(f"[Preview] Will rename: {dir_name} -> {new_name}")
                    else:
                        safe_rename(old_path, new_path)
        
        remove_short_audio_files(target_folder, dry_run)
                        
    except Exception as e:
        print(f"Error processing folder: {str(e)}")

def rename_files_underscore_to_dash(target_folder: str, dry_run: bool = False) -> None:
    """Replace underscores with dashes in all file and folder names"""
    print("\n=== Converting underscores to dashes in names ===")
    try:
        for root, dirs, files in os.walk(target_folder, topdown=False):
            for file_name in files:
                if '_' in file_name:
                    old_path = os.path.join(root, file_name)
                    new_name = file_name.replace('_', '-')
                    new_path = os.path.join(root, new_name)
                    
                    if dry_run:
                        print(f"[Preview] Will rename file: {file_name} -> {new_name}")
                    else:
                        safe_rename(old_path, new_path)
            
            for dir_name in dirs:
                if '_' in dir_name:
                    old_path = os.path.join(root, dir_name)
                    new_name = dir_name.replace('_', '-')
                    new_path = os.path.join(root, new_name)
                    
                    if dry_run:
                        print(f"[Preview] Will rename directory: {dir_name} -> {new_name}")
                    else:
                        safe_rename(old_path, new_path)
                        
    except Exception as e:
        print(f"Error converting underscores to dashes: {str(e)}")

def main():
    parser = argparse.ArgumentParser(
        description='Process audio folders: remove specific folders, convert Chinese names to Pinyin, and remove short audio files'
    )
    parser.add_argument('target_folder', help='Target folder path to process')
    parser.add_argument('--dry-run', action='store_true', help='Preview mode, no actual changes')
    
    args = parser.parse_args()
    
    print(f"Start processing folder: {args.target_folder}")
    print(f"Mode: {'Preview' if args.dry_run else 'Execute'}")
    
    rename_folders_to_pinyin(args.target_folder, args.dry_run)
    rename_speaker_folders(args.target_folder, args.dry_run)
    rename_files_underscore_to_dash(args.target_folder, args.dry_run)
    
    print("\nProcessing completed")

if __name__ == "__main__":
    main()
