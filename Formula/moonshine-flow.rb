class MoonshineFlow < Formula
  desc "Push-to-talk transcription daemon for macOS using Moonshine"
  homepage "https://github.com/NAKAK10/moonshine-flow"
  # stable-release: updated by GitHub Actions on release publish.
  # stable-release-start
  url "https://github.com/NAKAK10/moonshine-flow/archive/refs/tags/v0.0.1-beta.9.tar.gz"
  sha256 "c58107b77d0684c0c8743634523d13a8aa200bc8d3a4c9b876ea09873465c5d3"
  version "0.0.1-beta.9"
  # stable-release-end
  head "https://github.com/NAKAK10/moonshine-flow.git", branch: "main"
  preserve_rpath
  skip_clean "libexec/README.md"
  skip_clean "libexec/pyproject.toml"
  skip_clean "libexec/uv.lock"

  depends_on "portaudio"
  depends_on "python@3.11"
  depends_on "uv"

  def install
    libexec.install buildpath.children
    libexec.install buildpath/"README.md"
    libexec.install buildpath/"pyproject.toml"
    libexec.install buildpath/"uv.lock"

    python = Formula["python@3.11"].opt_bin/"python3.11"
    uv = Formula["uv"].opt_bin/"uv"
    ENV["UV_PYTHON"] = python
    ENV["UV_PYTHON_DOWNLOADS"] = "never"
    system uv, "sync", "--project", libexec, "--frozen"

    (bin/"moonshine-flow").write <<~SH
      #!/bin/bash
      exec "#{python}" "#{opt_libexec}/src/moonshine_flow/homebrew_bootstrap.py" \
        --libexec "#{opt_libexec}" \
        --var-dir "#{var}/moonshine-flow" \
        --python "#{python}" \
        --uv "#{uv}" \
        -- \
        "$@"
    SH
    chmod 0755, bin/"moonshine-flow"
  end

  test do
    assert_match "moonshine-flow", shell_output("#{bin}/moonshine-flow --help")
    assert_predicate opt_libexec/"README.md", :exist?
    probe = shell_output(
      <<~EOS
        #{opt_libexec}/.venv/bin/python -c "import ctypes; import moonshine_voice; from pathlib import Path; lib = Path(moonshine_voice.__file__).resolve().with_name('libmoonshine.dylib'); ctypes.CDLL(str(lib)); print('moonshine-runtime-ok')"
      EOS
    )
    assert_match "moonshine-runtime-ok", probe
  end
end
