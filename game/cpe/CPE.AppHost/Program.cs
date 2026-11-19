// Start services first; the launcher opens the game after verified setup.
var builder = DistributedApplication.CreateBuilder(args);
var root = Environment.GetEnvironmentVariable("ALPTHA_ROOT")
    ?? Path.GetFullPath(Path.Combine(builder.AppHostDirectory, "..", "..", ".."));
var goDirectory = Path.Combine(root, "game", "cpe", "go-cache");
var nodeDirectory = Path.Combine(root, "game", "cpe", "node-bridge");
var goBinary = Environment.GetEnvironmentVariable("CPE_GO_CACHE_EXE")
    ?? throw new InvalidOperationException("Start Alptha with bootstrap.py so Go is built first.");
builder.AddExecutable("alptha-go-cache", goBinary, goDirectory,
        "--host", "127.0.0.1", "--port", "4311")
    .WithHttpEndpoint(port: 4311, targetPort: 4311, name: "http", isProxied: false);
builder.AddExecutable("alptha-node-bridge",
        Environment.GetEnvironmentVariable("CPE_NODE_EXE") ?? "node", nodeDirectory,
        "server.js", "--host", "127.0.0.1", "--port", "4310")
    .WithHttpEndpoint(port: 4310, targetPort: 4310, name: "http", isProxied: false)
    .WithEnvironment("CPE_NODE_HOST", "127.0.0.1")
    .WithEnvironment("CPE_GO_CACHE_URL", "http://127.0.0.1:4311");
builder.Build().Run();
