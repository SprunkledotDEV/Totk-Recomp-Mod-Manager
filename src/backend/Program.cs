using System.Text.Json;
using Microsoft.Extensions.Logging;
using TkSharp.Core;
using TkSharp.Core.Models;
using TkSharp.Core.IO.Buffers;
using TkSharp.Core.IO.Caching;
using TkSharp.Core.IO.Parsers;
using TkSharp.Data.Embedded;
using TkSharp.IO.Readers;
using TkSharp.Merging;

// Adapter for TKMM-Team/TkSharp (MIT), pinned in THIRD_PARTY_NOTICES.md.
// Reads the recompiler's indexed image directly, with preceding mods as the base.
try {
    if (args.Length < 5 || args.Length > 6) throw new ArgumentException("Usage: backend GAME PACKAGE OUTPUT WORK BASE_OVERLAY [OPTIONS_JSON]");
    var logger = new MergeLogger();
    TkLog.Instance.Register(logger);
    var system = new SafeSystem(args[3]);
    using var input = File.OpenRead(args[1]);
    var mod = await new TkPackReader(system).ReadMod(new TkModContext(input: args[1], stream: input), CancellationToken.None)
              ?? throw new InvalidDataException("Empty TKCL package");
    var profile = new TkProfileMod(mod);
    profile.EnsureOptionSelection(applyPackagedDefaults: true);
    var metadata = new {
        name = mod.Name, description = mod.Description, version = mod.Version, author = mod.Author,
        gameVersion = mod.Changelog.GameVersion,
        groups = mod.OptionGroups.Select((g, i) => new {
            index = i, name = g.Name, description = g.Description, type = g.Type.ToString(),
            options = g.Options.Select(o => new { id = o.Id.ToString(), name = o.Name, description = o.Description }),
            defaults = profile.SelectedOptions[g].Select(o => o.Id.ToString())
        })
    };
    if (args[0] == "--inspect") {
        File.WriteAllText(args[2], JsonSerializer.Serialize(metadata));
        return 0;
    }
    if (args.Length == 6) {
        var selections = JsonSerializer.Deserialize<Dictionary<string, string[]>>(File.ReadAllText(args[5]))!;
        foreach (var (g, i) in mod.OptionGroups.Select((g, i) => (g, i))) {
            if (!selections.TryGetValue(i.ToString(), out var ids)) continue;
            var selected = g.Options.Where(o => ids.Contains(o.Id.ToString())).ToHashSet();
            if (selected.Count != ids.Distinct().Count()) throw new InvalidDataException("Unknown package option");
            if ((g.Type is OptionGroupType.Single or OptionGroupType.SingleRequired) && selected.Count > 1)
                throw new InvalidDataException("Select only one option in " + g.Name);
            if ((g.Type is OptionGroupType.MultiRequired or OptionGroupType.SingleRequired) && selected.Count == 0)
                throw new InvalidDataException("Select an option in " + g.Name);
            profile.SelectedOptions[g] = selected;
        }
    }
    var changes = new List<TkChangelog> { mod.Changelog };
    changes.AddRange(profile.SelectedOptions.OrderBy(x => x.Key.Priority)
        .SelectMany(x => x.Value.OrderBy(v => v.Priority)).Select(x => x.Changelog));
    foreach (var c in changes) {
        if (c.PatchFiles.Count + c.ExeFiles.Count + c.SubSdkFiles.Count + c.CheatFiles.Count > 0)
            throw new InvalidDataException("Package contains executable patches or cheats; these cannot run in the recompiled game.");
    }
    if (mod.Dependencies.Count > 0 || mod.OptionGroups.Any(g => g.Dependencies.Count > 0))
        throw new InvalidDataException("Package has dependencies. Export a resolved full RomFS from TKMM first.");
    using var rom = new IndexedRom(args[0], args[4]);
    new TkMerger(new SafeWriter(args[2], romfsOnly: true), rom,
        ["CNzh", "EUde", "EUen", "EUes", "EUfr", "EUit", "EUnl", "EUru", "JPja", "KRko", "TWzh", "USen", "USes", "USfr"])
        .Merge(changes);
    if (logger.Warnings.Count > 0)
        throw new InvalidDataException("TKMM could not merge cleanly:\n" + string.Join('\n', logger.Warnings));
    File.WriteAllText(Path.Combine(args[2], "package-info.json"), JsonSerializer.Serialize(new {
        name = mod.Name, version = mod.Version, author = mod.Author,
        options = profile.SelectedOptions.SelectMany(x => x.Value).Select(x => x.Name).ToArray(),
        files = changes.SelectMany(x => x.ChangelogFiles).Select(x => x.Canonical).ToArray()
    }));
    Console.WriteLine($"Merged {mod.Name} ({mod.Version}), packaged default options.");
    return 0;
} catch (Exception e) {
    Console.Error.WriteLine(e.ToString());
    return 1;
}

static class SafePath {
    public static string Join(string root, string name) {
        var fullRoot = Path.GetFullPath(root);
        var normalized = name.Replace('\\', '/');
        if (Path.IsPathRooted(name) || normalized.Split('/').Any(x => x is ".." or ".") || name.Contains(':'))
            throw new InvalidDataException("Unsafe package path: " + name);
        var path = Path.GetFullPath(Path.Combine(fullRoot, normalized));
        if (!path.StartsWith(fullRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Package path escapes its directory");
        return path;
    }
}
sealed class SafeWriter(string root, bool romfsOnly = false) : ITkModWriter {
    string relative = "";
    public Stream OpenWrite(string path) {
        // TkMerger.MergeIps unconditionally emits its default shop-limit IPS even
        // with no mod patches. Explicit package code patches were rejected above.
        if (romfsOnly && path.Replace('\\', '/').StartsWith("exefs/")) return new MemoryStream();
        var dest = SafePath.Join(root, Path.Combine(relative, path));
        Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
        return File.Create(dest);
    }
    public void SetRelativeFolder(string folder) { SafePath.Join(root, folder); relative = folder; }
}
sealed class SafeSource(string root) : ITkSystemSource {
    public Stream OpenRead(string path) => File.OpenRead(SafePath.Join(root, path));
    public bool Exists(string path) => File.Exists(SafePath.Join(root, path));
    public ITkSystemSource GetRelative(string path) => new SafeSource(SafePath.Join(root, path));
    public IEnumerable<string> EnumerateRomfsBuckets() => Directory.Exists(Path.Combine(root, "romfs"))
        ? Directory.GetDirectories(Path.Combine(root, "romfs"), "TKMM*").Select(p => Path.GetFileName(p)!) : [];
}
sealed class SafeSystem(string root) : ITkSystemProvider {
    public ITkModWriter GetSystemWriter(TkModContext context, bool enableRomfsBucketing = true)
        => new SafeWriter(SafePath.Join(root, context.Id.ToString()));
    public ITkSystemSource GetSystemSource(string path) => new SafeSource(SafePath.Join(root, path));
}
sealed class MergeLogger : ILogger {
    public List<string> Warnings { get; } = [];
    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
    public bool IsEnabled(LogLevel level) => level >= LogLevel.Warning;
    public void Log<TState>(LogLevel level, EventId id, TState state, Exception? error, Func<TState, Exception?, string> format) {
        if (!IsEnabled(level)) return;
        lock (Warnings) Warnings.Add(format(state, error));
    }
}
sealed class IndexedRom : ITkRom {
    readonly FileStream image;
    readonly string overlay;
    readonly Dictionary<string, (long Offset, int Size)> entries = [];
    readonly TkPackFileLookup packs;
    public int GameVersion { get; }
    public string NsoBinaryId { get; }
    public TkZstd Zstd { get; }
    public IDictionary<string, string> AddressTable { get; }
    public Dictionary<string, string>.AlternateLookup<ReadOnlySpan<char>> EventFlowVersions { get; }
    public Dictionary<string, string>.AlternateLookup<ReadOnlySpan<char>> EffectVersions { get; }
    public Dictionary<string, string>.AlternateLookup<ReadOnlySpan<char>> AiVersions { get; }
    public Dictionary<string, string>.AlternateLookup<ReadOnlySpan<char>> LogicVersions { get; }
    public Dictionary<string, string>.AlternateLookup<ReadOnlySpan<char>> SequenceVersions { get; }
    public IndexedRom(string game, string baseOverlay) {
        overlay = baseOverlay;
        image = File.OpenRead(Path.Combine(game, "romfs", "romfs.bin"));
        using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(game, "romfs", "index.json")));
        if (doc.RootElement.GetProperty("status").GetString() != "pass"
            || doc.RootElement.GetProperty("romfs_size").GetInt64() != image.Length)
            throw new InvalidDataException("Unverified or changed RomFS image");
        foreach (var row in doc.RootElement.GetProperty("files").EnumerateArray())
            entries.Add(row.GetProperty("path").GetString()!, (row.GetProperty("offset").GetInt64(), row.GetProperty("size").GetInt32()));
        GameVersion = RegionLangMaskParser.ParseVersion(Raw("System/RegionLangMask.txt"), out var nso);
        NsoBinaryId = nso;
        using var dictionaries = new MemoryStream(Raw("Pack/ZsDic.pack.zs"));
        Zstd = new TkZstd(dictionaries);
        AddressTable = AddressTableParser.ParseAddressTable(Raw($"System/AddressTable/Product.{GameVersion}.Nin_NX_NVN.atbl.byml.zs"), Zstd);
        byte[] Entry(string canonical) => Raw(AddressTable[canonical] + ".zs");
        EventFlowVersions = EventFlowFileEntryParser.ParseFileEntry(Entry("Event/EventFlow/EventFlowFileEntry.Product.byml"), Zstd);
        EffectVersions = EffectInfoParser.ParseFileEntry(Entry("Effect/EffectFileInfo.Product.Nin_NX_NVN.byml"), Zstd);
        AiVersions = StandardFileEntryParser.ParseStandardFileEntry(Entry("AI/FileEntry/FileEntry.Product.byml"), Zstd);
        LogicVersions = StandardFileEntryParser.ParseStandardFileEntry(Entry("Logic/FileEntry/FileEntry.Product.byml"), Zstd);
        SequenceVersions = StandardFileEntryParser.ParseStandardFileEntry(Entry("Sequence/FileEntry/FileEntry.Product.byml"), Zstd);
        using var lookup = TkEmbeddedDataSource.GetPackFileLookup();
        packs = new TkPackFileLookup(lookup);
    }
    byte[] Raw(string path) {
        var candidate = SafePath.Join(overlay, path);
        if (File.Exists(candidate)) return File.ReadAllBytes(candidate);
        if (!entries.TryGetValue(path, out var entry)) throw new FileNotFoundException(path);
        var data = new byte[entry.Size];
        lock (image) { image.Position = entry.Offset; image.ReadExactly(data); }
        return data;
    }
    public RentedBuffer<byte> GetVanilla(string path, out bool missing) {
        missing = false;
        if (!entries.ContainsKey(path) && !File.Exists(SafePath.Join(overlay, path)))
            return packs.GetNested(path, this, out missing);
        var data = Raw(path);
        if (TkZstd.IsCompressed(data)) data = Zstd.Decompress(data);
        var rented = RentedBuffer<byte>.Allocate(data.Length);
        data.CopyTo(rented.Span);
        return rented;
    }
    // Never skip resource accounting based on stock checksums when preceding mods may change the base.
    public bool IsVanilla(ReadOnlySpan<char> path, Span<byte> data, int version) => false;
    public bool IsVanillaAnyVersion(ReadOnlySpan<char> path, Span<byte> data) => false;
    public void Dispose() { image.Dispose(); Zstd.Dispose(); packs.Dispose(); }
}
