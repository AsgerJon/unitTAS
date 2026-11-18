package io.github.asgerjon.unittas.probe;

import java.io.File;
import java.lang.reflect.Method;
import java.nio.file.Path;
import net.minecraft.CrashReport;

/**
 * A crash report saved (the hook crash.saved, after CrashReport.saveToFile; SPEC.md 19.7 steps 9b and 10b): the game
 * is crashing (a client's own crash, or its integrated server's, which crashes it too; or a dedicated server's), so
 * the orchestrator hears it, with the report's file and what it says, before the JVM goes, and then the quit, with
 * reason crash (Probe.crashed, as 1.7.10's MixinMinecraft says it). No client class: a client's probe and a
 * dedicated server's both say it by this.
 */
final class ModernCrash {

	/** The report's save file, by its Mojang name: a Path from 1.21 on, a File in 1.20.1. */
	private static volatile Method saveFile;

	private ModernCrash() {
	}

	/** The report, as saved. */
	static void saved(CrashReport report) {
		Probe.crashed(file(report), report.getTitle(), report.getException());
	}

	/** The file the report was saved to, or null where it couldn't be. */
	private static File file(CrashReport report) {
		Method method = saveFile;
		if (method == null) {
			method = Members.method(CrashReport.class, "getSaveFile");
			saveFile = method;
		}
		Object saved = Members.call(method, report);
		if (saved instanceof Path path) {
			return path.toFile();
		}
		return (File) saved;
	}
}
