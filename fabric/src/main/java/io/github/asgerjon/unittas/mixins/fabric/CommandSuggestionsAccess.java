package io.github.asgerjon.unittas.mixins.fabric;

import com.mojang.brigadier.suggestion.Suggestions;
import net.minecraft.client.gui.components.CommandSuggestions;
import net.minecraft.util.FormattedCharSequence;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * The suggestions the server sent for the chat's text, the list the chat shows of them (null when none is), and the
 * usage it shows, for chat.read.
 */
@Mixin(CommandSuggestions.class)
public interface CommandSuggestionsAccess {

	@Accessor("pendingSuggestions")
	CompletableFuture<Suggestions> unittas$pending();

	@Accessor("commandUsage")
	List<FormattedCharSequence> unittas$usage();

	@Accessor("suggestions")
	CommandSuggestions.SuggestionsList unittas$shown();
}
