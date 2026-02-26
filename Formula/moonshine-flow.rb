class MoonshineFlow < Formula
  desc "Push-to-talk transcription daemon for macOS using Moonshine"
  homepage "https://github.com/MadHatterNakashima/moonshine-flow"
  # stable-release: updated by GitHub Actions on release publish.
  # stable-release-start
  url "https://github.com/NAKAK10/moonshine-flow/archive/refs/tags/v0.0.1-beta.5.tar.gz"
  sha256 "8fa914121fa31b333a19b2ca4241e90e31c8d7ad0b9a9287ccd1c4c436314c32"
  version "0.0.1-beta.5"
  # stable-release-end
  head "https://github.com/MadHatterNakashima/moonshine-flow.git", branch: "main"
  preserve_rpath

  depends_on "portaudio"
  depends_on "python@3.11"
  depends_on "uv"

  def install
    libexec.install buildpath.children

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
  end
end
