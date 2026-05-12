# ビルド関連情報

[English](build.en.md)

## GBSPlayerのビルド方法

> [!NOTE]
> 本ページは、各種ビルド環境が整っている前提で解説しています。

### プレイヤー ROM のビルド

#### GBS、GB、GBC のいずれかのファイルを用意

ファイルは `samples/gbs/` などに置いてください。曲名ファイルを使う場合は、用意したファイルと同じディレクトリに `<ファイル名>.names.txt` を置きます。

ファイル仕様は [曲名/曲長リストの仕様について](docs/songlist-format.md) を参照ください。

#### ビルド

下記コマンドでビルドします。

```powershell
make GBDK=C:/dev/gbdk GBS=samples/gbs/music.gbs
```

> [!NOTE]
> GBDK-2020を別の場所に配置した場合は`GBDK=`のパスを書き換えてください。


成果物は `build/gbs_player.gbc` に出力されます。

## Android Playerのビルドをコマンドラインのみで行う場合

### Androidビルド

#### SameBoyの取得

PowerShellで下記コマンドを実行して、SameBoy(GBエミュレータ)を取得します。

```powershell
python tools/fetch_sameboy.py
```

#### プレイヤー関連メタデータの生成

ROM を Android assets に反映させるために、下記コマンドを実行します。
曲名データなどを生成するコマンドです。

```bash
make android-assets GBDK=C:/dev/gbdk GBS=samples/gbs/music.gbs
```

#### APK のビルド

```powershell
cd apps/android
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:Path="$env:JAVA_HOME\bin;$env:Path"
.\gradlew.bat assembleDebug
```

APK は下記場所に出力されます。

```text
apps/android/app/build/outputs/apk/debug/app-debug.apk
```


### make cleanの動作について

```bash
make clean
```

このビルドでの`make clean` は生成ROMと中間ファイルをWindowsのごみ箱へ送ります。

> [!NOTE]
> ごみ箱APIが使えない環境では、物理削除せずプロジェクト内の `.trash/` へ移動します。
> 通常は再ビルド時に必要な生成物が上書きされるため、初回利用では `make clean` は不要です。

### フォントの対応文字を変更するには？

通常の ROM ビルドであれば生成済みの `src/player/jp_font.h` を使うため必須ではありません。<br>
対応する日本語を変更する際など、ユーザーにてフォントタイルを再生成する場合は、PowerShellで次を実行してください。

```powershell
python -m pip install Pillow fonttools
python tools/fetch_pkmnfont.py
python tools/gen_jp_font.py
```

配置先は `assets/fonts/pkmnfont/` です。
